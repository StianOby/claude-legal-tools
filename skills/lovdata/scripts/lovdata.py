#!/usr/bin/env python3
"""
lovdata.py — Hjelpeverktøy for Lovdata-ferdigheten

Laster ned, oppdaterer og søker i Lovdatas frie datapakker:
  - gjeldende-lover.tar.bz2        (NL: gjeldende lover)
  - gjeldende-sentrale-forskrifter.tar.bz2  (SF: gjeldende sentrale forskrifter)

API: https://api.lovdata.no/v1/publicData/list  (ingen autentisering)

Bruk:
  python lovdata.py update                     Sjekk og last ned oppdaterte pakker
  python lovdata.py status                     Vis nedlastningsstatus og datoer
  python lovdata.py index                      Bygg søkeindeks (kjøres automatisk etter update)
  python lovdata.py search <søkeord>           Søk i titler og innhold
  python lovdata.py get <dokid>                Hent full lovtekst (f.eks. NL/lov/2005-06-17-62)
  python lovdata.py get <dokid> <paragraf>     Hent spesifikk paragraf (f.eks. §4-6 eller 4-6)

Tilstand og nedlastede data lagres i en skrivbar brukerkatalog (ikke i selve
ferdighetskatalogen, som ofte er skrivebeskyttet når skillet er installert).
Stien velges slik:
  1. $LOVDATA_DATA_DIR — hvis satt
  2. $XDG_CACHE_HOME/lovdata — hvis satt
  3. %LOCALAPPDATA%\\lovdata — på Windows
  4. ~/.cache/lovdata — ellers
"""

import argparse
import json
import os
import re
import sys
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- Konfigurasjon -----------------------------------------------------------

SKILL_DIR = Path(__file__).parent.parent  # skrivebeskyttet referansekatalog


def _resolve_data_root() -> Path:
    """Returner en skrivbar katalog for state.json og nedlastede datapakker.

    Skill-katalogen kan være skrivebeskyttet (f.eks. når skillet er installert
    via et plugin), så vi legger all skrivbar tilstand i en brukerkatalog.
    """
    env_dir = os.environ.get("LOVDATA_DATA_DIR")
    if env_dir:
        return Path(env_dir).expanduser()

    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "lovdata"

    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            return Path(local_appdata) / "lovdata"

    return Path.home() / ".cache" / "lovdata"


DATA_ROOT = _resolve_data_root()
STATE_FILE = DATA_ROOT / "state.json"
DATA_DIR = DATA_ROOT / "data"
INDEX_FILE = DATA_DIR / "index.json"

# Bakoverkompatibilitet: hvis en tidligere installasjon la state/data inn i
# selve skill-katalogen, og den fortsatt er lesbar, migrer dataene over til
# brukerkatalogen ved første kjøring.
LEGACY_STATE_FILE = SKILL_DIR / "state.json"
LEGACY_DATA_DIR = SKILL_DIR / "data"


def _ensure_data_root():
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _maybe_migrate_legacy():
    """Kopier gammel state.json/data/ fra skill-katalogen om de finnes og målet er tomt."""
    try:
        if LEGACY_STATE_FILE.exists() and not STATE_FILE.exists():
            _ensure_data_root()
            STATE_FILE.write_bytes(LEGACY_STATE_FILE.read_bytes())
        if LEGACY_DATA_DIR.exists() and LEGACY_DATA_DIR.is_dir():
            # Bare migrer hvis vi ikke allerede har data i ny katalog
            has_existing = DATA_DIR.exists() and any(DATA_DIR.iterdir())
            if not has_existing:
                _ensure_data_root()
                import shutil
                for item in LEGACY_DATA_DIR.iterdir():
                    target = DATA_DIR / item.name
                    if target.exists():
                        continue
                    if item.is_dir():
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)
    except Exception:
        # Migrering er best-effort; ikke krasj selv om legacy-katalogen er
        # skrivebeskyttet eller utilgjengelig.
        pass


API_BASE = "https://api.lovdata.no"

PACKAGES = {
    "gjeldende-lover": {
        "filename": "gjeldende-lover.tar.bz2",
        "description": "Gjeldende lover (NL)",
        "subdir": "nl",
    },
    "gjeldende-sentrale-forskrifter": {
        "filename": "gjeldende-sentrale-forskrifter.tar.bz2",
        "description": "Gjeldende sentrale forskrifter (SF)",
        "subdir": "sf",
    },
}

# --- Tilstandshåndtering -----------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"last_checked": None, "api_key": None, "packages": {}}


def save_state(state: dict):
    _ensure_data_root()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# --- API-kall ----------------------------------------------------------------

def get_package_list(api_key: str | None = None) -> list[dict]:
    url = f"{API_BASE}/v1/publicData/list"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_package(filename: str, dest: Path, api_key: str | None = None):
    url = f"{API_BASE}/v1/publicData/get/{filename}"
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    req = urllib.request.Request(url, headers=headers)
    print(f"  Laster ned {filename} ...", flush=True)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(dest, "wb") as f:
        f.write(data)
    print(f"  Lastet ned {len(data) // 1024} KB", flush=True)


# --- Pakke- og indekshåndtering ----------------------------------------------

def extract_package(archive_path: Path, extract_to: Path):
    extract_to.mkdir(parents=True, exist_ok=True)
    print(f"  Pakker ut til {extract_to} ...", flush=True)
    with tarfile.open(archive_path, "r:bz2") as tf:
        # Extract only the inner files (strip leading directory component)
        members = tf.getmembers()
        for member in members:
            # Flatten: remove leading directory (e.g. nl/ or sf/)
            parts = Path(member.name).parts
            if len(parts) >= 2:
                member.name = parts[-1]  # just the filename
            elif len(parts) == 1:
                continue  # skip the directory entry itself
            tf.extract(member, path=extract_to)
    print(f"  Pakket ut {len(members)} filer", flush=True)


def build_index(data_dir: Path) -> dict:
    """
    Bygger en søkeindeks over alle nedlastede lover og forskrifter.
    Returnerer en dict: {filename: {title, dokid, base, lastChange}}
    """
    index = {}
    for base_key, pkg in PACKAGES.items():
        subdir = data_dir / pkg["subdir"]
        if not subdir.exists():
            continue
        base_code = "NL" if pkg["subdir"] == "nl" else "SF"
        for xml_file in sorted(subdir.glob("*.xml")):
            try:
                with open(xml_file, encoding="utf-8") as f:
                    content = f.read(3000)
                title_m = re.search(r"<title>([^<]+)</title>", content)
                dokid_m = re.search(
                    r'class="dokid">DokumentID</dt><dd class="dokid">([^<]+)</dd>', content
                )
                last_m = re.search(
                    r'class="lastChangeInForce">Ikrafttredelse av siste endring</dt>'
                    r'<dd class="lastChangeInForce">([^<]+)</dd>',
                    content,
                )
                if dokid_m:
                    index[str(xml_file)] = {
                        "title": title_m.group(1).strip() if title_m else "",
                        "dokid": dokid_m.group(1).strip(),
                        "base": base_code,
                        "lastChange": last_m.group(1).strip() if last_m else "",
                        "filename": xml_file.name,
                    }
            except Exception:
                pass
    return index


# --- Søk og oppslag ----------------------------------------------------------

def search_index(index: dict, query: str, max_results: int = 15) -> list[dict]:
    """Søk i indeksen etter tittel eller dokid (case-insensitive)."""
    query_lower = query.lower()
    results = []
    for path, meta in index.items():
        score = 0
        if query_lower in meta["title"].lower():
            score += 2
        if query_lower in meta["dokid"].lower():
            score += 3
        if score:
            results.append({**meta, "_score": score, "_path": path})
    results.sort(key=lambda x: -x["_score"])
    return results[:max_results]


def get_law_text(xml_path: str, paragraph: str | None = None) -> str:
    """
    Hent tekst fra en XML-fil.
    Hvis paragraph er oppgitt (f.eks. '4-6' eller '§4-6'), hentes bare den paragrafen.
    """
    with open(xml_path, encoding="utf-8") as f:
        content = f.read()

    if paragraph:
        # Normalize: ensure it starts with §
        para_norm = paragraph.strip()
        if not para_norm.startswith("§"):
            para_norm = "§" + para_norm
        para_norm_nospace = para_norm.replace(" ", "")

        # Find the article with this data-name
        pattern = rf'<article[^>]*data-name="{re.escape(para_norm_nospace)}"'
        match = re.search(pattern, content)
        if not match:
            # Try with space: §\s*4-6
            para_digits = re.sub(r"[§\s]", "", para_norm)
            pattern2 = rf'<article[^>]*data-name="§\s*{re.escape(para_digits)}"'
            match = re.search(pattern2, content)
        if not match:
            return f"Paragraf {paragraph} ble ikke funnet i dette dokumentet."

        start = match.start()
        # Find the next sibling article at same nesting level
        next_article = re.search(r"<article[^>]*data-name=", content[start + 10 :])
        end = (start + 10 + next_article.start()) if next_article else (start + 8000)
        chunk = content[start:end]
    else:
        # Full document — strip header boilerplate, return body text
        body_start = content.find('<body>')
        chunk = content[body_start:] if body_start >= 0 else content

    # Strip HTML tags and clean whitespace
    text = re.sub(r"<[^>]+>", " ", chunk)
    text = re.sub(r"\s+", " ", text).strip()
    # Remove HTML entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"')
    return text


def find_by_dokid(index: dict, dokid: str) -> str | None:
    """Finn filsti for et gitt dokid."""
    dokid_clean = dokid.strip()
    for path, meta in index.items():
        if meta["dokid"].lower() == dokid_clean.lower():
            return path
    return None


# --- Kommandoer --------------------------------------------------------------

def cmd_update(args, state: dict) -> dict:
    """Sjekk og last ned oppdaterte pakker."""
    api_key = state.get("api_key")
    print("Sjekker tilgjengelige pakker fra api.lovdata.no ...")
    try:
        available = get_package_list(api_key)
    except Exception as e:
        print(f"FEIL: Kunne ikke hente pakkeoversikt: {e}", file=sys.stderr)
        sys.exit(1)

    pkg_map = {p["filename"]: p for p in available}
    state.setdefault("packages", {})
    _ensure_data_root()

    updated_any = False
    for pkg_key, pkg_info in PACKAGES.items():
        filename = pkg_info["filename"]
        remote = pkg_map.get(filename)
        if not remote:
            print(f"  Pakke ikke tilgjengelig: {filename}")
            continue

        remote_modified = remote.get("lastModified", "")
        local_modified = state["packages"].get(pkg_key, {}).get("lastModified", "")
        subdir = DATA_DIR / pkg_info["subdir"]

        needs_update = (
            remote_modified != local_modified
            or not subdir.exists()
            or not any(subdir.glob("*.xml"))
        )

        if needs_update:
            print(f"Oppdatering tilgjengelig for {pkg_info['description']}")
            print(f"  Fjernversjon: {remote_modified}  Lokal: {local_modified or 'ikke lastet ned'}")
            archive_path = DATA_DIR / filename
            download_package(filename, archive_path, api_key)
            extract_package(archive_path, subdir)
            archive_path.unlink()  # Remove archive after extraction
            state["packages"][pkg_key] = {
                "lastModified": remote_modified,
                "downloaded": datetime.now(timezone.utc).isoformat(),
            }
            updated_any = True
        else:
            print(f"  {pkg_info['description']}: oppdatert ({local_modified})")

    if updated_any:
        print("Bygger søkeindeks ...")
        index = build_index(DATA_DIR)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False)
        print(f"  Indekserte {len(index)} dokumenter")

    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    return state


def cmd_status(args, state: dict):
    """Vis status for nedlastede pakker."""
    print("=== Lovdata-pakkestatus ===")
    print(f"Datakatalog: {DATA_ROOT}")
    for pkg_key, pkg_info in PACKAGES.items():
        pkg_state = state.get("packages", {}).get(pkg_key, {})
        subdir = DATA_DIR / pkg_info["subdir"]
        file_count = len(list(subdir.glob("*.xml"))) if subdir.exists() else 0
        print(f"\n{pkg_info['description']}")
        print(f"  Sist oppdatert (remote): {pkg_state.get('lastModified', 'ukjent')}")
        print(f"  Lastet ned:              {pkg_state.get('downloaded', 'aldri')}")
        print(f"  Lokale filer:            {file_count} XML-filer")
    print(f"\nSist sjekket: {state.get('last_checked', 'aldri')}")
    if INDEX_FILE.exists():
        with open(INDEX_FILE, encoding="utf-8") as f:
            idx = json.load(f)
        print(f"Indeks:       {len(idx)} dokumenter")


def cmd_index(args, state: dict):
    """Bygg/oppdater søkeindeks."""
    print("Bygger søkeindeks ...")
    _ensure_data_root()
    index = build_index(DATA_DIR)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    print(f"Indekserte {len(index)} dokumenter")


def cmd_search(args, state: dict):
    """Søk i titler."""
    if not INDEX_FILE.exists():
        print("Ingen indeks funnet. Kjør 'python lovdata.py update' først.", file=sys.stderr)
        sys.exit(1)
    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)
    results = search_index(index, args.query)
    if not results:
        print(f"Ingen treff for '{args.query}'")
        return
    print(f"Treff for '{args.query}' ({len(results)} resultater):\n")
    for r in results:
        print(f"  [{r['base']}] {r['title']}")
        print(f"         DokID: {r['dokid']}  Sist endret: {r['lastChange'] or 'ukjent'}")
        print()


def cmd_get(args, state: dict):
    """Hent lovtekst for et dokid, evt. for en spesifikk paragraf."""
    if not INDEX_FILE.exists():
        print("Ingen indeks funnet. Kjør 'python lovdata.py update' først.", file=sys.stderr)
        sys.exit(1)
    with open(INDEX_FILE, encoding="utf-8") as f:
        index = json.load(f)

    path = find_by_dokid(index, args.dokid)
    if not path:
        print(f"Dokument ikke funnet: {args.dokid}", file=sys.stderr)
        # Try partial match
        results = search_index(index, args.dokid.split("/")[-1])
        if results:
            print("Mente du kanskje:")
            for r in results[:5]:
                print(f"  {r['dokid']} — {r['title']}")
        sys.exit(1)

    meta = index[path]
    paragraph = getattr(args, "paragraph", None)
    text = get_law_text(path, paragraph)

    print(f"=== {meta['title']} ===")
    print(f"DokID: {meta['dokid']}  |  Sist endret: {meta['lastChange'] or 'ukjent'}")
    if paragraph:
        print(f"Paragraf: {paragraph}")
    print()
    print(text)


# --- Inngangspunkt -----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("update", help="Sjekk og last ned oppdaterte pakker")
    subparsers.add_parser("status", help="Vis nedlastningsstatus")
    subparsers.add_parser("index", help="Bygg søkeindeks")

    p_search = subparsers.add_parser("search", help="Søk etter lover/forskrifter")
    p_search.add_argument("query", help="Søkeord (tittel eller dokid)")

    p_get = subparsers.add_parser("get", help="Hent lovtekst")
    p_get.add_argument("dokid", help="DokumentID, f.eks. NL/lov/2005-06-17-62")
    p_get.add_argument("paragraph", nargs="?", help="Paragraf, f.eks. §4-6 eller 4-6")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    _ensure_data_root()
    _maybe_migrate_legacy()
    state = load_state()

    if args.command == "update":
        state = cmd_update(args, state)
        save_state(state)
    elif args.command == "status":
        cmd_status(args, state)
    elif args.command == "index":
        cmd_index(args, state)
        save_state(state)
    elif args.command == "search":
        cmd_search(args, state)
    elif args.command == "get":
        cmd_get(args, state)


if __name__ == "__main__":
    main()
