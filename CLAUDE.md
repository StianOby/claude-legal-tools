# claude-legal-tools

A collection of Claude Code skills for working with legal and library sources
(Lovdata, EUR-Lex, HUDOC, ICJ, Nasjonalbiblioteket, etc.).

## Skill authoring rules

### Description length limit: 1024 characters

Every `SKILL.md` frontmatter `description:` field must be **≤ 1024 characters
after YAML parsing** (i.e. the joined string the loader sees, not the raw
source with line breaks and indentation). Skills with longer descriptions are
rejected by the loader.

This has been a recurring problem in this repo. When writing or editing a
description:

- Pack the trigger list densely — list keywords/identifiers as a
  comma-separated group, not as separate "or" clauses.
- Cut redundant phrasings of the same trigger (e.g. don't include both
  "fetch this old Norwegian newspaper" and "save these pages from
  Nasjonalbiblioteket" — one example per category is enough).
- Keep the structure: (1) when to use, (2) trigger keywords/URL patterns,
  (3) scope of material covered, (4) any sub-workflow variants, (5) what NOT
  to use it for.
- Verify before committing:

  ```bash
  python3 -c "
  import yaml, sys
  text = open(sys.argv[1]).read()
  fm = text.split('---', 2)[1]
  print(len(yaml.safe_load(fm)['description']))
  " skills/<name>/SKILL.md
  ```

  The number printed must be ≤ 1024.
