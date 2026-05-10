"""
Shared utilities for the icj skill.

Provides:
- HTTP fetch with a sensible User-Agent and basic retry.
- A persistent cache (data/cache/) with a manifest.json keyed by URL,
  recording fetch_timestamp, server Last-Modified, ETag, and a content
  SHA-256 hash. Used both for serving cached payloads and for freshness
  checks via HEAD requests.
- ISO-2 country code helpers used by the declarations module.
- Small helpers for printing JSON or human output uniformly.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "[icj] The 'requests' package is required. "
        "Install with: pip install requests beautifulsoup4 --break-system-packages\n"
    )
    raise

USER_AGENT = (
    "icj-skill/1.0 (+https://github.com/) "
    "Python-requests; harvests public ICJ pages for offline analysis"
)
BASE = "https://www.icj-cij.org"

# Default TTL for jurisdiction data (in seconds): 14 days.
DEFAULT_TTL = 14 * 24 * 3600

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache"
MANIFEST_PATH = CACHE_DIR / "manifest.json"


# --- HTTP ---------------------------------------------------------------

def _session() -> "requests.Session":
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def http_get(url: str, *, timeout: int = 30, retries: int = 2) -> "requests.Response":
    """GET with one retry on transient errors. Raises on final failure."""
    s = _session()
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = s.get(url, timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_exc = e
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed after {retries + 1} attempts: {last_exc}")


def http_head(url: str, *, timeout: int = 15) -> "requests.Response":
    s = _session()
    return s.head(url, timeout=timeout, allow_redirects=True)


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
    with MANIFEST_PATH.open() as f:
        raw = json.load(f)
    return {url: CacheEntry.from_json(e) for url, e in raw.items()}


def _save_manifest(manifest: dict[str, CacheEntry]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(
            {url: e.to_json() for url, e in manifest.items()},
            f,
            indent=2,
            sort_keys=True,
        )
    tmp.replace(MANIFEST_PATH)


def _cache_path_for(url: str) -> Path:
    """Map a URL to a stable on-disk filename."""
    # Use a short hash to avoid pathological URL lengths and special chars.
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    # Keep a hint of the URL in the filename so manual cache inspection is sane.
    tail = url.rsplit("/", 1)[-1] or "index"
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
            if payload_path.exists():
                return payload_path.read_text(encoding="utf-8"), entry, False
    # Refetch
    r = http_get(url)
    text = r.text
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload_path = _cache_path_for(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload_path.write_text(text, encoding="utf-8")
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


def freshness_report(urls: list[str]) -> list[dict]:
    """For each URL, compare the cached entry to a HEAD request.

    Returns a list of dicts with: url, cached_at (iso), age_days, server_last_modified,
    head_status, changed (bool: server reports a different Last-Modified or ETag,
    or the URL is uncached).
    """
    manifest = _load_manifest()
    out = []
    for url in urls:
        entry = manifest.get(url)
        info: dict = {"url": url}
        if entry is None:
            info.update(
                {
                    "cached": False,
                    "changed": True,
                    "reason": "not in cache",
                }
            )
            out.append(info)
            continue
        info["cached"] = True
        info["cached_at"] = time.strftime(
            "%Y-%m-%d %H:%M UTC", time.gmtime(entry.fetched_at)
        )
        info["age_days"] = round((time.time() - entry.fetched_at) / 86400, 1)
        info["cached_last_modified"] = entry.last_modified
        info["cached_etag"] = entry.etag
        try:
            r = http_head(url)
            info["head_status"] = r.status_code
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
                if info["age_days"] > 14:
                    changed = True
                    reason = (
                        "no Last-Modified/ETag from server; cache older than 14 days"
                    )
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

# Minimal mapping for the states with a deposited Article 36(2) declaration.
# The skill resolves user input ("Norway") -> ISO-2 ("no") via this table.
# Keep it conservative — when a state is absent here, declarations.show falls
# back to a substring search across the live declarations index.
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
