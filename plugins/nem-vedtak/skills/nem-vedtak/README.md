# NEM-vedtak

Lets Claude look up and search the appeal decisions of **NEM** (Den nasjonale
forskningsetiske komité for medisin og helsefag), published at
[forskningsetikk.no](https://www.forskningsetikk.no/om-oss/komiteer-og-utvalg/nem/sok-i-nems-vedtak/).
NEM hears appeals against REK decisions under helseforskningsloven; there are
about 234 published decisions from 2009 on.

The site's own search ignores quotation marks, so it cannot do phrase searches.
This skill can therefore download **all** decisions into a folder on your
computer (about 3 MB of Markdown, roughly 15 seconds) and search them with
exact phrases, regular expressions and filters: outcome, keyword (emneord),
research-ethics principle, statute, REK, institution and year.

A single decision you can name (case number, title or link) is always
fetched live from the site, with no copy. For searches across decisions,
Claude in Cowork first asks whether to keep the copy in a connected folder
(`<connected folder>/nem-vedtak/`, through the local shell), so it persists
between sessions and you can open the files yourself. Searching across
decisions needs this copy; without a connected folder, only single
decisions can be looked up.

This is a niche tool. `kildesjekk` does not need it; install it if you work
with research ethics.

## Quick test

```bash
python3 scripts/nem.py get "NEM 2021/169"
python3 scripts/nem.py sync --dir ~/nem-vedtak
python3 scripts/nem.py search --dir ~/nem-vedtak "utsatt offentlighet"
python3 scripts/nem.py search --dir ~/nem-vedtak --utfall "gis medhold" --emneord Samtykke
```

## Layout

```
nem-vedtak/
├── SKILL.md
├── README.md
├── local-route.md            # shared (shared/local-route/)
├── scripts/
│   ├── nem.py                # single CLI; standard library only
│   └── pack_for_local.sh     # shared (shared/local-route/)
└── evals/
    └── evals.json
```

Offline tests live in the repository at `tests/nem-vedtak/`, not in the
plugin: `python tests/nem-vedtak/test_nem.py`.
