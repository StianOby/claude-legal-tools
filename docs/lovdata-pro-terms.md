# lovdata-pro and Lovdata's terms of use

Lovdata Pro is governed by Lovdata's brukervilkår, section 2.2 *Lovdatas
innloggingstjenester*:
<https://lovdata.no/artikkel/brukervilkar_for_lovdatas_tjenester/1324>.
(The free API used by `lovdata-api` is under NLOD 2.0 and is not affected.)
The section is quoted in full in `plugins/lovdata-pro/skills/lovdata-pro/README.md`.

**Last compared: 2026-10-28.**

## Review routine

Compare section 2.2 with the README quote from time to time: whenever
lovdata-pro is worked on, and at least every few months. If the wording has
changed, update the README quote and its date, check the decisions below
against the new text, and update the date above.

## Maintainer's decisions (2026-10-28)

How the skill relates to each part of section 2.2:

- **AI use, document type.** The skill's scope (court decisions,
  preparatory works) is "enkeltdokumenter opprinnelig utarbeidet av
  offentlige organer". There is no collection whitelist in `load()` or
  `search()`. Literature and other non-public material are outside that
  scope, but the skill never looks for them; a user who pushes it to fetch
  them takes that responsibility.
- **"ikke lagrer innholdet eller bruker det til trening".** Storage in the
  user's own local folder or the user's own areas of Anthropic's cloud
  (conversation, outputs) is not what the clause covers. Training is the
  user's setting ("Help improve our AI models"); Claude cannot read it, so the
  skill reminds the user once per conversation (SKILL.md, Step 0) and the
  README lists it as a requirement.
- **"Massenedlasting av innholdet er ikke tillatt."** The skill always
  fetches single documents. Reading a large document in parts (`section()`,
  `page()`, or dump mode looping over a multi-MB NOU) is still one document,
  not "massenedlasting".
- **kildesjekk** looks up one cited document per reference: not
  "massenedlasting".
- **Quotations** in answers and kildesjekk worklists rest on sitatretten in
  åndsverkloven.
