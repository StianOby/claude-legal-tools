"""
Shared utilities for the icj skill.

Provides:
- HTTP fetch (standard library urllib) with a sensible User-Agent and retry.
- A persistent cache (~/.cache/icj/, or $ICJ_CACHE_DIR) with a manifest.json
  keyed by URL, recording fetch_timestamp, server Last-Modified, ETag, and a
  content SHA-256 hash. Used both for serving cached payloads and for
  freshness checks via HEAD requests.
- ISO-2 country code helpers used by the declarations module.
- Small helpers for printing JSON or human output uniformly.

No third-party packages are required.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

USER_AGENT = (
    "icj-skill/2.0 (+https://github.com/StianOby/claude-legal-tools) "
    "Python-urllib; reads public ICJ pages for legal research"
)
BASE = "https://www.icj-cij.org"

# Default TTL for jurisdiction data (in seconds): 14 days.
DEFAULT_TTL = 14 * 24 * 3600

_default_cache = Path.home() / ".cache" / "icj"
CACHE_DIR = Path(os.environ.get("ICJ_CACHE_DIR", _default_cache))
MANIFEST_PATH = CACHE_DIR / "manifest.json"


# --- HTTP ---------------------------------------------------------------

@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def _request(url: str, *, method: str = "GET", timeout: int = 30) -> Response:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
                                 method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = b"" if method == "HEAD" else r.read()
        return Response(r.status, {k: v for k, v in r.headers.items()}, body)


def http_get(url: str, *, timeout: int = 30, retries: int = 2) -> Response:
    """GET with retries on transient errors (network, 5xx). Raises on final failure."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return _request(url, timeout=timeout)
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last_exc}")


def http_head(url: str, *, timeout: int = 15) -> Response:
    try:
        return _request(url, method="HEAD", timeout=timeout)
    except urllib.error.HTTPError as e:
        return Response(e.code, {k: v for k, v in e.headers.items()}, b"")


# --- Cache manifest -----------------------------------------------------

@dataclass
class CacheEntry:
    url: str
    path: str  # path relative to CACHE_DIR
    fetched_at: float
    last_modified: Optional[str]
    etag: Optional[str]
    sha256: str

    def to_json(self) -> dict:
        return {
            "url": self.url,
            "path": self.path,
            "fetched_at": self.fetched_at,
            "last_modified": self.last_modified,
            "etag": self.etag,
            "sha256": self.sha256,
        }

    @classmethod
    def from_json(cls, d: dict) -> "CacheEntry":
        return cls(
            url=d["url"],
            path=d["path"],
            fetched_at=d["fetched_at"],
            last_modified=d.get("last_modified"),
            etag=d.get("etag"),
            sha256=d["sha256"],
        )


def _load_manifest() -> dict[str, CacheEntry]:
    if not MANIFEST_PATH.exists():
        return {}
    try:
        raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {url: CacheEntry.from_json(e) for url, e in raw.items()}


def _save_manifest(manifest: dict[str, CacheEntry]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({url: e.to_json() for url, e in manifest.items()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, MANIFEST_PATH)


def _cache_path_for(url: str) -> Path:
    """Map a URL to a stable on-disk filename."""
    # Use a short hash to avoid pathological URL lengths and special chars.
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    # Keep a hint of the URL in the filename so manual cache inspection is sane.
    tail = url.rstrip("/").rsplit("/", 1)[-1] or "index"
    safe_tail = "".join(c if c.isalnum() or c in "-_." else "_" for c in tail)[:60]
    return CACHE_DIR / f"{safe_tail}.{h}.html"


def fetch_cached(
    url: str,
    *,
    force_refresh: bool = False,
    ttl: int = DEFAULT_TTL,
) -> tuple[str, CacheEntry, bool]:
    """
    Return (html, entry, was_refetched).

    If a fresh cache entry exists (younger than ttl seconds), return it.
    Otherwise fetch from the network, update the manifest, return the new copy.
    `force_refresh=True` always re-fetches.
    """
    manifest = _load_manifest()
    entry = manifest.get(url)
    now = time.time()
    if entry and not force_refresh:
        age = now - entry.fetched_at
        if age < ttl:
            payload_path = CACHE_DIR / entry.path
            if payload_path.exists() and payload_path.stat().st_size > 0:
                return payload_path.read_text(encoding="utf-8"), entry, False
    # Refetch
    r = http_get(url)
    text = r.text
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload_path = _cache_path_for(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = payload_path.with_name(payload_path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, payload_path)
    entry = CacheEntry(
        url=url,
        path=payload_path.name,
        fetched_at=now,
        last_modified=r.headers.get("Last-Modified"),
        etag=r.headers.get("ETag"),
        sha256=sha,
    )
    manifest[url] = entry
    _save_manifest(manifest)
    return text, entry, True


def get_cached_only(url: str) -> Optional[tuple[str, CacheEntry]]:
    """Return cached payload + entry if present, else None. Never hits the network."""
    manifest = _load_manifest()
    entry = manifest.get(url)
    if not entry:
        return None
    payload_path = CACHE_DIR / entry.path
    if not payload_path.exists():
        return None
    return payload_path.read_text(encoding="utf-8"), entry


def freshness_report(urls: list[str], *, ttl: int = DEFAULT_TTL) -> list[dict]:
    """For each URL, compare the cached entry to a HEAD request.

    Returns a list of dicts with: url, cached_at (iso), age_days, server_last_modified,
    head_status, changed (bool: server reports a different Last-Modified or ETag,
    or the URL is uncached, or — when the server sends no validators — the cache
    is older than the TTL).
    """
    manifest = _load_manifest()
    ttl_days = ttl / 86400
    out = []
    for url in urls:
        entry = manifest.get(url)
        info: dict = {"url": url}
        if entry is None:
            info.update({"cached": False, "changed": True, "reason": "not in cache"})
            out.append(info)
            continue
        info["cached"] = True
        info["cached_at"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(entry.fetched_at))
        info["age_days"] = round((time.time() - entry.fetched_at) / 86400, 1)
        info["cached_last_modified"] = entry.last_modified
        info["cached_etag"] = entry.etag
        try:
            r = http_head(url)
            info["head_status"] = r.status
            srv_lm = r.headers.get("Last-Modified")
            srv_etag = r.headers.get("ETag")
            info["server_last_modified"] = srv_lm
            info["server_etag"] = srv_etag
            changed = False
            reason = None
            if srv_lm and entry.last_modified and srv_lm != entry.last_modified:
                changed = True
                reason = "Last-Modified differs"
            elif srv_etag and entry.etag and srv_etag != entry.etag:
                changed = True
                reason = "ETag differs"
            elif not srv_lm and not srv_etag:
                # Server gives no validators — fall back to TTL-based suspicion.
                if info["age_days"] > ttl_days:
                    changed = True
                    reason = f"no Last-Modified/ETag from server; cache older than {ttl_days:g} days"
            info["changed"] = changed
            if reason:
                info["reason"] = reason
        except Exception as e:  # pragma: no cover
            info["head_status"] = None
            info["changed"] = True
            info["reason"] = f"HEAD failed: {e}"
        out.append(info)
    return out


# --- Country codes ------------------------------------------------------

# Mapping for the states with a deposited Article 36(2) declaration
# (checked against the live /declarations index, September 2026).
# The skill resolves user input ("Norway") -> ISO-2 ("no") via this table.
# When a state is absent here, declarations.show falls back to a substring
# search across the live declarations index.
NAME_TO_ISO2 = {
    "australia": "au",
    "austria": "at",
    "barbados": "bb",
    "belgium": "be",
    "botswana": "bw",
    "bulgaria": "bg",
    "cambodia": "kh",
    "cameroon": "cm",
    "canada": "ca",
    "costa rica": "cr",
    "cote d'ivoire": "ci",
    "côte d'ivoire": "ci",
    "ivory coast": "ci",
    "cyprus": "cy",
    "democratic republic of the congo": "cg",
    "drc": "cg",
    "denmark": "dk",
    "djibouti": "dj",
    "dominica": "dm",
    "dominican republic": "do",
    "egypt": "eg",
    "equatorial guinea": "gq",
    "estonia": "ee",
    "finland": "fi",
    "gambia": "gm",
    "georgia": "ge",
    "germany": "de",
    "greece": "gr",
    "guinea": "gn",
    "guinea-bissau": "gw",
    "haiti": "ht",
    "honduras": "hn",
    "hungary": "hu",
    "iceland": "is",
    "india": "in",
    "iran": "ir",
    "ireland": "ie",
    "italy": "it",
    "japan": "jp",
    "latvia": "lv",
    "lesotho": "ls",
    "liberia": "lr",
    "liechtenstein": "li",
    "lithuania": "lt",
    "luxembourg": "lu",
    "madagascar": "mg",
    "malawi": "mw",
    "malta": "mt",
    "marshall islands": "mh",
    "mauritius": "mu",
    "mexico": "mx",
    "netherlands": "nl",
    "new zealand": "nz",
    "nicaragua": "ni",
    "nigeria": "ng",
    "norway": "no",
    "pakistan": "pk",
    "panama": "pa",
    "paraguay": "py",
    "peru": "pe",
    "philippines": "ph",
    "poland": "pl",
    "portugal": "pt",
    "romania": "ro",
    "senegal": "sn",
    "slovakia": "sk",
    "somalia": "so",
    "spain": "es",
    "sudan": "sd",
    "suriname": "sr",
    "swaziland": "sz",
    "eswatini": "sz",
    "sweden": "se",
    "switzerland": "ch",
    "timor-leste": "tl",
    "east timor": "tl",
    "togo": "tg",
    "uganda": "ug",
    "united kingdom": "gb",
    "uk": "gb",
    "great britain": "gb",
    "uruguay": "uy",
}


def resolve_state(name_or_code: str) -> Optional[str]:
    """Return ISO-2 for a state name or pass through a 2-letter code (lowercased)."""
    s = name_or_code.strip().lower()
    if len(s) == 2 and s.isalpha():
        return s
    if s in NAME_TO_ISO2:
        return NAME_TO_ISO2[s]
    # Try a unique prefix match.
    matches = [code for name, code in NAME_TO_ISO2.items() if name.startswith(s)]
    matches = list(set(matches))
    if len(matches) == 1:
        return matches[0]
    return None


# --- I/O helpers --------------------------------------------------------

def emit(payload, *, as_json: bool, human_fn=None) -> None:
    """Print payload as JSON or via a human-friendly formatter."""
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if human_fn is not None:
        human_fn(payload)
        return
    # Default: pretty JSON
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def warn(msg: str) -> None:
    sys.stderr.write(f"[icj] {msg}\n")
