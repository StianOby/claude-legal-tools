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
  python lovdata.py search <søkeord>           Søk i titler, korttitler (aml, fvl ...) og DokID
  python lovdata.py find <ord> [dokid]         Fulltekstsøk i bestemmelsene (--sf, --phrase)
  python lovdata.py get <dokid>                Hent full lovtekst (f.eks. NL/lov/2005-06-17-62)
  python lovdata.py get <dokid> <paragraf>     Hent spesifikk paragraf (f.eks. §4-6 eller 4-6)
  python lovdata.py get <dokid> kap4           Hent et helt kapittel
  python lovdata.py get <dokid> emkn/a8        Hent en seksjon eller artikkel i et vedlegg
  python lovdata.py get <dokid> --nn           Nynorsk-versjonen (Grunnloven)
  python lovdata.py get <dokid> --out FIL      Skriv teksten til fil i stedet for stdout

<dokid> kan også være LOV-2005-06-17-62, FOR-…, en lovdata.no-URL eller en
entydig korttittel/forkortelse (aml, Grunnloven).

Tilstand og nedlastede data lagres i en skrivbar brukerkatalog (ikke i selve
ferdighetskatalogen, som ofte er skrivebeskyttet når skillet er installert).
Stien velges slik:
  1. $LOVDATA_DATA_DIR — hvis satt
  2. $XDG_CACHE_HOME/lovdata — hvis satt
  3. %LOCALAPPDATA%\\lovdata — på Windows
  4. ~/.cache/lovdata — ellers
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.parse
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
    # Skriv til en midlertidig fil og bytt inn atomisk, slik at en avbrutt
    # nedlasting aldri etterlater et halvt arkiv under det endelige navnet.
    tmp = dest.with_name(dest.name + ".part")
    size = 0
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as f:
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            f.write(block)
            size += len(block)
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"tom nedlasting: {filename}")
    os.replace(tmp, dest)
    print(f"  Lastet ned {size // 1024} KB", flush=True)


# --- Pakke- og indekshåndtering ----------------------------------------------

def extract_package(archive_path: Path, extract_to: Path):
    """Pakk ut arkivet flatt til extract_to.

    Utpakkingen skjer først til en midlertidig søsterkatalog som deretter
    byttes inn for den gamle. Feiler utpakkingen, står den gamle katalogen
    urørt, og indeksen peker aldri på en halvferdig fil-samling.
    """
    extract_to.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Pakker ut til {extract_to} ...", flush=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=extract_to.name + ".", dir=extract_to.parent))
    count = 0
    try:
        with tarfile.open(archive_path, "r:bz2") as tf:
            for member in tf:
                if not member.isfile():
                    continue  # katalogoppføringer, lenker o.l.
                # Flat struktur: behold bare filnavnet (fjerner nl/ eller sf/ og
                # hindrer samtidig at stier med ../ havner utenfor katalogen).
                name = Path(member.name).name
                if not name or name.startswith("."):
                    continue
                src = tf.extractfile(member)
                if src is None:
                    continue
                with src, open(tmp_dir / name, "wb") as out:
                    shutil.copyfileobj(src, out)
                count += 1
        if count == 0:
            raise RuntimeError(f"arkivet {archive_path.name} inneholdt ingen filer")
        old_dir = None
        if extract_to.exists():
            old_dir = extract_to.with_name(extract_to.name + ".old")
            if old_dir.exists():
                shutil.rmtree(old_dir)
            os.replace(extract_to, old_dir)
        os.replace(tmp_dir, extract_to)
        if old_dir is not None:
            shutil.rmtree(old_dir, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    print(f"  Pakket ut {count} filer", flush=True)


def _read_header(xml_file: Path) -> str:
    """Les dokumenthodet (til og med metadata-listen <dl>), ikke hele filen."""
    with open(xml_file, encoding="utf-8") as f:
        content = f.read(8000)
        while "</dl>" not in content and "</header>" not in content:
            more = f.read(8000)
            if not more:
                break
            content += more
    return content


def _dd(content: str, cls: str) -> str:
    m = re.search(rf'<dd class="{cls}">(.*?)</dd>', content, flags=re.S)
    return html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


def build_index(data_dir: Path) -> dict:
    """
    Bygger en søkeindeks over alle nedlastede lover og forskrifter.
    Returnerer en dict: {"<subdir>/<filnavn>": {title, titleShort, dokid, base,
    lastChange, filename}}. Nøkkelen er relativ til datakatalogen, slik at
    indeksen fortsatt virker om datakatalogen flyttes.
    """
    index = {}
    for base_key, pkg in PACKAGES.items():
        subdir = data_dir / pkg["subdir"]
        if not subdir.exists():
            continue
        base_code = "NL" if pkg["subdir"] == "nl" else "SF"
        for xml_file in sorted(subdir.glob("*.xml")):
            try:
                content = _read_header(xml_file)
                title_m = re.search(r"<title>([^<]+)</title>", content)
                dokid = _dd(content, "dokid")
                if dokid:
                    index[f"{pkg['subdir']}/{xml_file.name}"] = {
                        "title": html.unescape(title_m.group(1)).strip() if title_m else "",
                        "titleShort": _dd(content, "titleShort"),
                        "dokid": dokid,
                        "base": base_code,
                        "lastChange": _dd(content, "lastChangeInForce"),
                        "dateInForce": _dd(content, "dateInForce"),
                        "filename": xml_file.name,
                    }
            except Exception:
                pass
    return index


def index_path(key: str) -> Path:
    """Filsti for en indeksnøkkel (relativ til DATA_DIR; eldre indekser brukte absolutte stier)."""
    p = Path(key)
    return p if p.is_absolute() else DATA_DIR / key


def _save_index(index: dict):
    tmp = INDEX_FILE.with_name(INDEX_FILE.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    os.replace(tmp, INDEX_FILE)


def _load_index() -> dict:
    if not INDEX_FILE.exists():
        print("Ingen indeks funnet. Kjør 'python lovdata.py update' først.", file=sys.stderr)
        sys.exit(1)
    with open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


# --- Søk og oppslag ----------------------------------------------------------

def _short_forms(title_short: str) -> list[str]:
    """Lovdatas korttittel har formen «Arbeidsmiljøloven – aml»; returner
    begge delene (uten avsluttende punktum) i små bokstaver. En del med
    parentes («Grunnloven (bokmål)») gir også formen uten parentesen."""
    out = []
    for p in re.split(r"\s+[–-]\s+", title_short):
        p = p.strip().rstrip(".").lower()
        if not p:
            continue
        out.append(p)
        bare = re.sub(r"\s*\([^)]*\)\s*$", "", p).strip()
        if bare and bare != p:
            out.append(bare)
    return out


def _is_nynorsk(path: str) -> bool:
    """Grunnloven finnes i to filer med samme DokID; nynorsk-filen heter *-nn.xml."""
    return path.endswith("-nn.xml")


def search_index(index: dict, query: str, max_results: int = 15) -> list[dict]:
    """Søk i indeksen etter tittel, korttittel/forkortelse eller dokid (case-insensitive).

    En forkortelse eller korttittel («aml», «Grl.», «Grunnloven») treffer
    eksakt og rangeres først; deretter delstrengtreff i tittel og
    korttittel. Et søk med flere ord treffer også når hvert ord står et
    sted i tittelen eller korttittelen («arbeidsmiljø lov»). Lover rangeres
    foran forskrifter og delegeringsvedtak med samme poengsum.
    """
    q = query.strip().rstrip(".").lower()
    if not q:
        return []
    words = q.split()
    results = []
    for path, meta in index.items():
        score = 0
        short = meta.get("titleShort", "")
        short_l = short.lower()
        title_l = meta["title"].lower()
        forms = _short_forms(short) if short else []
        if q in forms:
            score += 6
        elif short and q in short_l:
            score += 3
        if q in meta["dokid"].lower():
            score += 3
        if q in title_l:
            score += 2
        if not score and len(words) > 1 and all(w in title_l or w in short_l for w in words):
            score += 1
        if score:
            if meta["dokid"].startswith("NL/"):
                score += 1
            results.append({**meta, "_score": score, "_path": path})
    results.sort(key=lambda x: (-x["_score"], _is_nynorsk(x["_path"]), x["title"]))
    return results[:max_results]


_BLOCK_TAGS = r"</?(article|section|h1|h2|h3|h4|h5|h6|p|li|dd|dt|tr|div|ul|ol|table|thead|tbody|caption)[^>]*>"

_MARK = "\x01"  # midlertidig markør for listepunkt, fjernes i _html_to_text


def _list_marker(m: re.Match) -> str:
    """Behold bokstav/nummer fra <li data-name="a."> som tekst, slik at
    «bokstav a» i et ledd kan siteres og gjenfinnes."""
    return "\n" + _MARK + html.unescape(m.group(1)) + "\n"


# Fotnotehenvisning og -etikett. Markøren hindrer at fotnotetallet smelter
# sammen med et tall foran (se tests/test_html_to_text.py).
_FN_REF = re.compile(r'<sup[^>]*\bclass="footnotereference"[^>]*>(.*?)</sup>', re.I | re.S)
_FN_LABEL = re.compile(r'<span[^>]*\bclass="footnoteLabel"[^>]*>(.*?)</span>', re.I | re.S)
# Øvrige <sup> er eksponenter (m<sup>2</sup>, cm<sup>3</sup>).
_SUP = re.compile(r"<sup>([^<]*)</sup>", re.I)
_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _fn_marker(m: re.Match) -> str:
    return "[fn " + re.sub(r"<[^>]+>", "", m.group(1)).strip() + "]"


def _html_to_text(chunk: str) -> str:
    """Konverter HTML-fragment til ren tekst med bevart avsnittsstruktur."""
    # Fotnoter: «protokoll 3[fn 5]» i teksten, «[fn 5] Gjelder ...» i fotnoten
    chunk = _FN_REF.sub(_fn_marker, chunk)
    chunk = _FN_LABEL.sub(_fn_marker, chunk)
    chunk = _SUP.sub(lambda m: m.group(1).translate(_SUPERSCRIPT)
                     if m.group(1).isdigit() else "^" + m.group(1), chunk)
    # Listepunkter: skriv ut markøren (a., 1., ...) før teksten
    chunk = re.sub(r'<li[^>]*\sdata-name="([^"]+)"[^>]*>', _list_marker, chunk, flags=re.I)
    # Blokknivå-tagger blir linjeskift; inline-tagger (span, a, ...) fjernes sporløst
    chunk = re.sub(_BLOCK_TAGS, "\n", chunk, flags=re.I)
    # Celleskille. Kun sluttag — matcher man også starttag blir separatoren doblet ("| |").
    chunk = re.sub(r"</(td|th)>", " | ", chunk, flags=re.I)
    chunk = re.sub(r"<br\s*/?>", "\n", chunk, flags=re.I)
    text = re.sub(r"<[^>]+>", "", chunk)
    text = html.unescape(text).replace("\xa0", " ")

    text = re.sub(r"[ \t]+", " ", text)
    lines: list[str] = []
    pending_marker = ""
    for line in text.split("\n"):
        line = line.strip().strip("|").strip()
        if not line:
            continue
        if line.startswith(_MARK):
            # Listepunktets tekst ligger i et eget blokkelement på neste linje;
            # sett markøren foran den («a. når arbeidet er ...»).
            pending_marker = line[len(_MARK):] + " "
            continue
        lines.append(pending_marker + line)
        pending_marker = ""
    if pending_marker:
        lines.append(pending_marker.strip())
    return "\n".join(lines).strip()


_CHAPTER_RE = re.compile(r"^(?:kap(?:ittel|\.)?|chapter)\s*([0-9]+[A-Za-z]*)$", re.I)


def _element_end(content: str, start: int, tag: str) -> int:
    """Posisjon rett etter slutt-taggen som lukker elementet <tag> som starter
    ved start, med hensyn til nøstede elementer av samme type."""
    depth = 0
    for m in re.finditer(rf"<{tag}\b[^>]*>|</{tag}>", content[start:]):
        depth += -1 if m.group(0).startswith("</") else 1
        if depth == 0:
            return start + m.end()
    return len(content)


# Konvensjonsvedleggene i menneskerettsloven er delt i seksjoner og
# artikler med sammensatte navn: emkn (EMK på norsk), emkn/a8 (artikkel 8),
# emkn/p1 (protokoll 1), emkn/p1/a1 (protokoll 1 artikkel 1). Brukere skriver
# gjerne «emkn art 8» eller «emkn protokoll 1 art. 1»; oversett til
# Lovdatas navn.
_SECTION_ALIAS_RE = re.compile(
    r"([a-zæøå]+)"
    r"(?:\s*/?\s*(?:protokoll|prot\.?|p)\s*(?:nr\.?\s*)?(\d+))?"
    r"(?:\s*/?\s*(?:artikkel|art\.?|a)\s*(\d+[a-z]?))?",
    re.I,
)


def _section_name(para: str) -> str:
    """«emkn art 8» -> «emkn/a8», «emkn p1 a1» -> «emkn/p1/a1»; ellers uendret."""
    m = _SECTION_ALIAS_RE.fullmatch(para.strip())
    if not m or not (m.group(2) or m.group(3)):
        return para
    name = m.group(1)
    if m.group(2):
        name += "/p" + m.group(2)
    if m.group(3):
        name += "/a" + m.group(3).lower()
    return name


def get_law_text(xml_path: str | Path, paragraph: str | None = None) -> str:
    """
    Hent tekst fra en dokumentfil (XHTML, til tross for .xml-endelsen).
    Hvis paragraph er oppgitt (f.eks. '4-6' eller '§4-6'), hentes bare den paragrafen;
    'kap4' / 'kapittel 4' henter hele kapittelet. Et vedleggs- eller
    seksjonsnavn virker også ('emkn' = EMK på norsk i menneskerettsloven),
    og det samme gjør én artikkel eller protokoll i et vedlegg ('emkn/a8',
    'emkn/p1', 'emkn/p1/a1', eller 'emkn art 8').
    """
    with open(xml_path, encoding="utf-8") as f:
        content = f.read()

    para = paragraph.strip() if paragraph else None
    chap = _CHAPTER_RE.match(para) if para else None
    # Navngitt seksjon: kapitler heter kap4, men vedlegg og konvensjoner har
    # egne navn (menneskerettsloven: emkn, spn, bkn, kdkn, crpdn, oskn ...).
    sec_name = None
    if chap:
        sec_name = "kap" + chap.group(1)
    elif para and re.fullmatch(r"[A-Za-zæøåÆØÅ][\w./ -]*", para):
        sec_name = _section_name(para)
    if sec_name:
        # Seksjoner (kapitler, vedlegg, protokoller) er <section>; en enkelt
        # artikkel i et vedlegg (emkn/a8) er <article>.
        m = re.search(rf'<(section|article)\b[^>]*data-name="{re.escape(sec_name)}"', content, flags=re.I)
        if not m:
            names = sorted(set(re.findall(r'<section[^>]*data-name="([^"]+)"', content)))
            what = f"Kapittel {chap.group(1)}" if chap else f"Seksjonen {sec_name!r}"
            listing = (" Tilgjengelige seksjoner: " + ", ".join(names)) if names else ""
            if any("/" in n for n in names):
                listing += (". Enkeltartikler heter <seksjon>/a<nr>, f.eks. emkn/a8 "
                            "eller emkn/p1/a1")
            return f"{what} ble ikke funnet i dette dokumentet.{listing}"
        chunk = content[m.start():_element_end(content, m.start(), m.group(1).lower())]
    elif paragraph:
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
        # Avslutt på neste paragraf-artikkel eller seksjonsslutt — unngår at
        # neste kapitteloverskrift lekker inn, og kutter ikke vilkårlig etter N tegn.
        nxt = re.search(r"<article[^>]*data-name=|</section>", content[start + 10 :])
        end = (start + 10 + nxt.start()) if nxt else len(content)
        chunk = content[start:end]
    else:
        # Full document — hopp over header (metadata + innholdsfortegnelse), returner body-tekst
        header_end = content.find("</header>")
        if header_end >= 0:
            chunk = content[header_end + len("</header>"):]
        else:
            body_start = content.find("<body>")
            chunk = content[body_start:] if body_start >= 0 else content

    return _html_to_text(chunk)


_PROVISION_START = re.compile(r'<article class="legalArticle"[^>]*data-name="([^"]+)"')


def _plain(chunk: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", chunk))).strip()


def find_text(index: dict, query: str, *, only: str | None = None,
              include_sf: bool = False, nynorsk: bool = False,
              phrase: bool = False) -> list[dict]:
    """Fulltekstsøk i bestemmelsene (paragrafer og konvensjonsartikler).

    Treffer en bestemmelse når hvert ord i `query` står i teksten (som
    delstreng, uten hensyn til store/små bokstaver), eller hele `query`
    ordrett med phrase=True. Søker i lovene (NL); forskriftene bare med
    include_sf, siden de er sju ganger så mange filer. `only` er en
    indeksnøkkel som begrenser søket til ett dokument.

    Returnerer én rad per bestemmelse, bestemmelser der hele frasen står
    ordrett først, deretter lover før forskrifter og flest forekomster først:
    {dokid, title, titleShort, provision, snippet, exact, count}.
    """
    q = re.sub(r"\s+", " ", query.strip().lower())
    if not q:
        return []
    words = [q] if phrase else q.split(" ")
    if only:
        paths = [only]
    else:
        paths = [p for p, meta in index.items()
                 if (include_sf or meta["dokid"].startswith("NL/"))
                 and _is_nynorsk(p) == nynorsk]
    hits = []
    for path in sorted(paths):
        meta = index[path]
        try:
            content = index_path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        low = content.lower()
        if not all(w in low for w in words):
            continue  # billig forhåndsfilter før teksten deles opp
        starts = list(_PROVISION_START.finditer(content))
        for i, m in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(content)
            text = _plain(content[m.start():end])
            tl = text.lower()
            if not all(w in tl for w in words):
                continue
            pos = tl.find(q) if q in tl else tl.find(words[0])
            a, b = max(0, pos - 120), min(len(text), pos + len(q) + 160)
            hits.append({
                "dokid": meta["dokid"],
                "title": meta["title"],
                "titleShort": meta.get("titleShort", ""),
                "provision": m.group(1),
                "snippet": ("…" if a else "") + text[a:b] + ("…" if b < len(text) else ""),
                "exact": q in tl,
                "count": tl.count(q) if q in tl else sum(tl.count(w) for w in words),
            })
    hits.sort(key=lambda h: (not h["exact"], not h["dokid"].startswith("NL/"), -h["count"]))
    return hits


def _pick_language(paths: list[str], nynorsk: bool = False) -> str | None:
    """Grunnloven har to filer med samme DokID. Velg bokmål med mindre
    nynorsk er bedt om (og finnes)."""
    if not paths:
        return None
    preferred = [p for p in paths if _is_nynorsk(p) == nynorsk]
    return (preferred or paths)[0]


def find_by_dokid(index: dict, dokid: str, nynorsk: bool = False) -> str | None:
    """Finn filsti for et gitt dokid."""
    dokid_clean = dokid.strip().lower()
    paths = [p for p, meta in index.items() if meta["dokid"].lower() == dokid_clean]
    return _pick_language(paths, nynorsk)


_LOVDATA_URL_RE = re.compile(
    r"^https?://(?:www\.)?lovdata\.no/(?:pro/)?(?:#?/?document/|dokument/)?"
    r"(?:(?P<base>[A-Z]+)/)?(?P<kind>lov|forskrift)/(?P<id>\d{4}-\d{2}-\d{2}(?:-\d+)?)"
    r"(?P<rest>.*)$",
    re.I,
)
_LOVDATA_REF_RE = re.compile(r"^(?P<kind>LOV|FOR)-(?P<id>\d{4}-\d{2}-\d{2}(?:-\d+)?)$", re.I)
_KIND_ID_RE = re.compile(
    r"^(?:(?P<base>[A-Z]+)/)?(?P<kind>lov|forskrift)/(?P<id>\d{4}-\d{2}-\d{2}(?:-\d+)?)$", re.I)


def resolve_ref(index: dict, raw: str, nynorsk: bool = False):
    """Finn filsti for det brukeren oppga som dokument.

    Godtar DokID (NL/lov/2005-06-17-62), Lovdatas referanseform
    (LOV-2005-06-17-62, FOR-1996-12-06-1127), lov/… og forskrift/… uten
    base, lovdata.no-URL-er (også med «/§4-6» på slutten) og korttitler
    eller forkortelser som «aml» og «Grunnloven» når de er entydige.

    Returnerer (sti, paragraf_fra_url, feilmelding); sti er None ved feil.
    """
    s = raw.strip()
    para = None
    kind = ident = None
    m = _LOVDATA_URL_RE.match(urllib.parse.unquote(s))
    if m:
        kind, ident = m.group("kind"), m.group("id")
        pm = re.search(r"§\s*([\w-]+)", m.group("rest") or "")
        if pm:
            para = pm.group(1)
    elif _LOVDATA_REF_RE.match(s):
        m = _LOVDATA_REF_RE.match(s)
        kind = "lov" if m.group("kind").upper() == "LOV" else "forskrift"
        ident = m.group("id")
    elif _KIND_ID_RE.match(s):
        m = _KIND_ID_RE.match(s)
        path = find_by_dokid(index, s, nynorsk) if m.group("base") else None
        if path:
            return path, None, None
        kind, ident = m.group("kind"), m.group("id")

    if kind:
        suffix = f"/{kind.lower()}/{ident}"
        paths = [p for p, meta in index.items() if meta["dokid"].lower().endswith(suffix)]
        # En lov ligger i NL; en forskrift oftest i SF, ellers i DEL/INS/STV.
        paths.sort(key=lambda p: (not index[p]["dokid"].startswith(("NL/", "SF/")), p))
        path = _pick_language(paths, nynorsk)
        if path:
            return path, para, None
        return None, None, f"Fant ikke {kind} {ident} i de frie pakkene."

    # Korttittel eller forkortelse: bare når den peker på ett dokument.
    q = s.rstrip(".").lower()
    hits = {}
    for p, meta in index.items():
        if meta.get("titleShort") and q in _short_forms(meta["titleShort"]):
            hits.setdefault(meta["dokid"], []).append(p)
    if len(hits) == 1:
        # Slå opp på DokID, ikke på treffet: «Grunnloven» står bare i
        # bokmålsfilens korttittel, men --nn skal likevel gi nynorsk.
        return find_by_dokid(index, next(iter(hits)), nynorsk), None, None
    if len(hits) > 1:
        return None, None, (f"«{s}» er tvetydig: " + ", ".join(sorted(hits))
                            + ". Oppgi DokID.")
    return None, None, None


# --- Kommandoer --------------------------------------------------------------

def cmd_update(args, state: dict) -> dict:
    """Sjekk og last ned oppdaterte pakker."""
    api_key = state.get("api_key")
    print("Sjekker tilgjengelige pakker fra api.lovdata.no ...")
    try:
        available = get_package_list(api_key)
    except Exception as e:
        print(f"FEIL: Kunne ikke hente pakkeoversikt: {e}", file=sys.stderr)
        if INDEX_FILE.exists():
            # Lokale data fra forrige vellykkede update er fortsatt brukbare.
            # Ikke oppdater last_checked: sjekken ble ikke gjort.
            print(_stale_data_warning(state), file=sys.stderr)
            return state
        sys.exit(1)

    pkg_map = {p["filename"]: p for p in available}
    state.setdefault("packages", {})
    _ensure_data_root()

    updated_any = False
    missing = []
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
            try:
                download_package(filename, archive_path, api_key)
                extract_package(archive_path, subdir)
            except Exception as e:
                # extract_package bytter bare inn en ferdig utpakket katalog,
                # så de gamle filene står urørt når noe feiler her.
                print(f"FEIL: {pkg_info['description']} kunne ikke oppdateres: {e}",
                      file=sys.stderr)
                if subdir.exists() and any(subdir.glob("*.xml")):
                    print("  Bruker de lokale filene fra forrige nedlasting "
                          f"({local_modified or 'ukjent dato'}).", file=sys.stderr)
                else:
                    missing.append(pkg_info["description"])
                continue
            finally:
                archive_path.unlink(missing_ok=True)
            state["packages"][pkg_key] = {
                "lastModified": remote_modified,
                "downloaded": datetime.now(timezone.utc).isoformat(),
            }
            save_state(state)  # husk denne pakken selv om neste skulle feile
            updated_any = True
        else:
            print(f"  {pkg_info['description']}: oppdatert ({local_modified})")

    if updated_any or not INDEX_FILE.exists():
        print("Bygger søkeindeks ...")
        index = build_index(DATA_DIR)
        _save_index(index)
        print(f"  Indekserte {len(index)} dokumenter")

    if missing:
        save_state(state)
        print("FEIL: Ingen lokale data for: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)

    state["last_checked"] = datetime.now(timezone.utc).isoformat()
    return state


def _stale_data_warning(state: dict) -> str:
    dates = ", ".join(
        f"{PACKAGES[k]['description']}: {v.get('lastModified') or 'ukjent'}"
        for k, v in (state.get("packages") or {}).items() if k in PACKAGES
    )
    return ("ADVARSEL: Fortsetter med lokale data som kan være utdatert"
            + (f" ({dates})" if dates else "")
            + ". Si fra til brukeren at teksten ikke er sjekket mot dagens versjon.")


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
    _save_index(index)
    print(f"Indekserte {len(index)} dokumenter")


def cmd_search(args, state: dict):
    """Søk i titler, korttitler og DokID."""
    index = _load_index()
    results = search_index(index, args.query)
    if not results:
        print(f"Ingen treff for '{args.query}'")
        return
    print(f"Treff for '{args.query}' ({len(results)} resultater):\n")
    for r in results:
        lang = "  (nynorsk — hent med get --nn)" if _is_nynorsk(r["_path"]) else ""
        print(f"  [{r['base']}] {r['title']}{lang}")
        if r.get("titleShort"):
            print(f"         Korttittel: {r['titleShort']}")
        print(f"         DokID: {r['dokid']}  Sist endret: {r['lastChange'] or 'ukjent'}")
        print()


def cmd_find(args, state: dict):
    """Fulltekstsøk i bestemmelsene."""
    index = _load_index()
    only = None
    if args.dokid:
        only, _, problem = resolve_ref(index, args.dokid, nynorsk=args.nn)
        if not only:
            print(f"Dokument ikke funnet: {args.dokid}" + (f" — {problem}" if problem else ""),
                  file=sys.stderr)
            sys.exit(1)
    hits = find_text(index, args.query, only=only, include_sf=args.sf,
                     nynorsk=args.nn, phrase=args.phrase)
    scope = index[only]["dokid"] if only else ("lover og forskrifter" if args.sf else "lovene")
    if not hits:
        print(f"Ingen bestemmelser i {scope} inneholder '{args.query}'.")
        return
    docs = len({h["dokid"] for h in hits})
    shown = hits[: args.max]
    print(f"'{args.query}' i {scope}: {len(hits)} bestemmelser i {docs} "
          + ("dokument" if docs == 1 else "dokumenter")
          + (f", viser de {len(shown)} første (--max for flere)" if len(shown) < len(hits) else "")
          + ":\n")
    for h in shown:
        name = h["titleShort"] or h["title"]
        prov = h["provision"].replace("§", "§ ", 1) if h["provision"].startswith("§") else h["provision"]
        print(f"  {name} — {prov}   ({h['dokid']})")
        print(f"      {h['snippet']}")
        print()


def cmd_get(args, state: dict):
    """Hent lovtekst for et dokid, evt. for en spesifikk paragraf eller et kapittel."""
    index = _load_index()
    nynorsk = getattr(args, "nn", False)

    path, url_para, problem = resolve_ref(index, args.dokid, nynorsk=nynorsk)
    if not path:
        print(f"Dokument ikke funnet: {args.dokid}" + (f" — {problem}" if problem else ""),
              file=sys.stderr)
        # Try partial match
        results = search_index(index, args.dokid.rstrip("/").split("/")[-1])
        if results:
            print("Mente du kanskje:")
            for r in results[:5]:
                print(f"  {r['dokid']} — {r['title']}")
        sys.exit(1)

    meta = index[path]
    if nynorsk and not _is_nynorsk(path):
        print(f"Merk: {meta['dokid']} finnes bare på bokmål i pakkene.", file=sys.stderr)
    file_path = index_path(path)
    if not file_path.exists():
        print(f"Filen for {meta['dokid']} finnes ikke lenger ({file_path}). "
              "Kjør 'python lovdata.py index' for å bygge indeksen på nytt.", file=sys.stderr)
        sys.exit(1)
    paragraph = getattr(args, "paragraph", None) or url_para
    text = get_law_text(file_path, paragraph)

    header = [f"=== {meta['title']} ==="]
    if meta.get("titleShort"):
        header.append(f"Korttittel: {meta['titleShort']}")
    header.append(f"DokID: {meta['dokid']}  |  Sist endret: {meta['lastChange'] or 'ukjent'}")
    # Ikrafttredelse kan være «Kongen bestemmer»: en vedtatt, men ennå ikke
    # ikraftsatt lov ligger i pakken side om side med den som gjelder.
    if meta.get("dateInForce"):
        header.append(f"Ikrafttredelse: {meta['dateInForce']}")
    if paragraph:
        header.append(f"Paragraf: {paragraph}")

    out = getattr(args, "out", None)
    if out:
        out_path = Path(out).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header) + "\n\n" + text + "\n")
        print("\n".join(header))
        print(f"Skrev {len(text)} tegn til {out_path}")
        return

    print("\n".join(header))
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

    p_find = subparsers.add_parser("find", help="Fulltekstsøk i bestemmelsene")
    p_find.add_argument("query", help="Ord som alle skal stå i bestemmelsen")
    p_find.add_argument("dokid", nargs="?", help="Søk bare i dette dokumentet (DokID, LOV-…, aml …)")
    p_find.add_argument("--phrase", action="store_true", help="Søk etter hele uttrykket ordrett")
    p_find.add_argument("--sf", action="store_true", help="Ta med forskriftene (tregere)")
    p_find.add_argument("--nn", action="store_true", help="Søk i nynorsk-versjonen (Grunnloven)")
    p_find.add_argument("--max", type=int, default=20, help="Maks antall treff som vises (standard 20)")

    p_get = subparsers.add_parser("get", help="Hent lovtekst")
    p_get.add_argument("dokid", help="DokID (NL/lov/2005-06-17-62), LOV-2005-06-17-62, "
                                     "lovdata.no-URL eller entydig korttittel (aml)")
    p_get.add_argument("paragraph", nargs="?",
                       help="Paragraf (§4-6 eller 4-6), kapittel (kap4) eller seksjon/artikkel (emkn, emkn/a8)")
    p_get.add_argument("--nn", action="store_true", help="Nynorsk-versjonen (finnes for Grunnloven)")
    p_get.add_argument("--out", metavar="FIL", help="Skriv teksten til denne filen i stedet for stdout")

    # Windows-konsollen bruker cp1252 som standard; lovtekst inneholder tegn
    # utenfor den (f.eks. kyrilliske bokstaver og typografiske mellomrom).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

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
    elif args.command == "find":
        cmd_find(args, state)
    elif args.command == "get":
        cmd_get(args, state)


if __name__ == "__main__":
    main()
