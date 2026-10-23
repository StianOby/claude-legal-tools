# eea-lex

Pure-Python skill that lets Claude answer EEA questions about EU law from
EFTA's own sources on www.efta.int:

- **EEA-Lex factsheets**: whether an EU act has been incorporated into the
  EEA Agreement, its stage, annex, Joint Committee Decision, EEA entry into
  force and the Icelandic/Norwegian translations.
- **EEA Joint Committee Decisions (JCDs)**: dates, acts, publication, and
  whether the JCD is in the Official Journal yet (checked in Cellar). If it
  isn't, the text comes from EFTA's PDF. EUR-Lex only gets JCDs months after
  adoption.
- **The EEA Agreement as it stands**: EFTA's consolidated main part,
  annexes and protocols, including an act's annex entry with the EFTA
  adaptations and the footnote naming the JCD.
- **Article 103**: JCDs waiting for an EFTA State's constitutional
  requirements.

See `SKILL.md` for the workflow. Quick test:

```bash
python3 scripts/eea_lex.py factsheet "Regulation 2016/679"
python3 scripts/eea_lex.py jcd 154/2018
python3 scripts/eea_lex.py agreement annex XI --find 32016R0679
python3 scripts/eea_lex.py pending103 --state NO
```

## Layout

```
eea-lex/
├── SKILL.md
├── README.md
├── scripts/
│   └── eea_lex.py          # single self-contained CLI; stdlib only
└── evals/
    └── evals.json          # task-eval prompts
```

Offline tests live in the repository at `tests/eea-lex/`, not in the plugin
(they do not ship to users): `python tests/eea-lex/test_eea_lex.py`. The
plan and the site facts behind the skill are in `docs/eea-lex.md`.

## Requirements

- **Python 3.9+**, standard library only.
- **PDF text** (JCD lists, JCDs, annexes): `pdftotext` from poppler-utils, or
  `pip install pypdf`. Either works; the parsers are tested on both.

## Access

www.efta.int puts a Cloudflare challenge on every client whose User-Agent
starts with `Mozilla/`. The script sends its own honest UA
(`eea-lex-skill/<version>`), waits a second between requests and follows at
most three redirects. If the site ever challenges the script, it stops with
exit code 3 and SKILL.md switches to a read-only browser route.

## Caveat

EEA-Lex and EFTA's consolidated texts are published for information. The
authentic texts are those in the OJ (EEA section) and the EEA Supplement.
