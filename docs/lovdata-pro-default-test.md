# lovdata-pro: which Lovdata Pro is the default?

lovdata-pro works on both the new Lovdata Pro (pro2) and Lovdata Pro
Klassisk, which Lovdata keeps through 2027 (`docs/lovdata-pro2.md`). SKILL.md
Step 0 names one **default** URL; the other is the fallback. This test picks
the default. Run it once now (round 1, after the smoke test in round 0) and
again in **mid/late 2027**, before Klassisk goes away. Agreed with the
maintainer on 2026-11-11.

## Rounds

- **Round 0 — smoke test (pro2 only).** Before measuring anything: in
  Cowork, paste the helper on pro2 and run `isLoggedIn()`, `load()` of
  HR-2016-2554-P (both candidates), `load("avgjorelse/rt-2000-1811")`,
  `load()` of NOU 2022:8, `grep(path, "(77)")`, `page()`, `section()` on the
  NOU, `search("HR-2016-2554-P", 5)`, `search("tomtefeste", 5, {bases:
  ["HRA"]})`, `stats()`. Compare the text of HR-2016-2554-P avsnitt 77 and
  one NOU section with the page as drawn. Fix what fails before round 1.
- **Round 1 — comparison.** Every task below, once per site (**1 run +
  repeat outliers**).
- **2027 rerun.** Same tasks, same protocol; add new tasks if the sites
  have changed (e.g. advanced search, below).

## Tasks

Each task is a natural user prompt, run as written so the whole skill path
is tested (resolve, load, find, quote), not only the helper.

| Id | Kind | Prompt (Norwegian, as a user would write it) |
|---|---|---|
| S1 | HR, paragraph | Hva sier Høyesterett i HR-2016-2554-P avsnitt 77? Siter avsnittet. |
| S2 | Rt. + page | Siter det Høyesterett sier i Rt. 2000 s. 1811 (Finanger I) på s. 1827. |
| S3 | RG | Hvilken domstol avsa RG 2009 s. 1, og hva ble resultatet? Siter domsslutningen. |
| S4 | Lagmannsrett | Siter domsslutningen i LB-2014-76577. |
| S5 | Tingrett | Siter domsslutningen i TOSL-2021-35560. |
| S6 | Metadata | Hvem var partene og prosessfullmektigene i LG-2008-135938? |
| S7 | NOU, large | Siter første avsnitt i kapittel 1 i NOU 2022:8. |
| S8 | NOU, old | Hva står i punkt 3.4 i NOU 1984:18? Siter første avsnitt. |
| S9 | Ot.prp. | Siter første avsnitt i kapittel 1 i Ot.prp. nr. 3 (1998-99). |
| S10 | Prop. L | Siter første avsnitt i kapittel 1 i Prop. 154 L (2016-2017). |
| S11 | Innst. | Siter komiteens første merknad i Innst. 409 L (2020-2021). |
| S12 | Meld. St. | Hva heter Meld. St. 17 (2020-2021)? Siter første avsnitt i kapittel 1. (Not in pro2: tests the fallback.) |
| K1 | kildesjekk batch | A kildesjekk of a short test text with ten Lovdata references (S1–S11 minus one), each with a quotation; one quotation altered by one word, one with a wrong pinpoint. Build the text in the Cowork session from the S-task quotes; never check it in (Lovdata text). |
| T1 | Topic research | Finn Høyesterettsavgjørelser om tomtefeste fra 2015 og senere, velg de tre mest relevante, og siter ett sentralt avsnitt fra hver. |
| F1 | Forarbeider | Hent forarbeidene til den nye mineralloven (NOU 2022:8, Prop. 71 L (2024-2025) og innstillingen), og finn hva de sier om konsultasjon med samiske interesser. Siter ett avsnitt fra hvert dokument. |

## How a run is done

- **One fresh Cowork conversation per task and site**, same model, logged
  in to both sites beforehand (sign-ins persist in the browser pane).
- **Order alternates** per task (S1: Klassisk first, S2: pro2 first, …) so
  neither site always gets a warm pane.
- **Forcing the site.** Start the prompt with: *"(Test: bruk Lovdata Pro på
  `<URL>` i stedet for standardadressen i SKILL.md Steg 0. Kjør `date +%s`
  i Bash før første og etter siste steg, kjør `await __lp.stats({reset:
  true})` rett etter at hjelperen er limt inn og `await __lp.stats()` til
  slutt, og rapporter tallene.)"* with `<URL>` =
  `https://pro2.lovdata.no/` or `https://lovdata.no/pro/?forceFullVersion=true`.
- **Re-pasting resets the meter**: a navigation or reload wipes `__lp`,
  and the new paste starts `stats()` from zero. Read `__lp.stats()` before
  any navigation away from the tab's page, and add up the readings.
- **No document text in the results file**: record paths, counts, times,
  yes/no; quotations are compared in the session, not written down.

## What is recorded per run

| Field | How |
|---|---|
| Wall time (s) | the two `date +%s` stamps |
| Cowork usage | the session's usage/token figure as Cowork shows it, read by the maintainer (blank if none is shown) |
| Returned chars | `__lp.stats().returnedChars`: characters the helper sent into the conversation |
| Helper calls | `__lp.stats().calls` (per function: n, chars, ms) |
| Fetches | `__lp.stats().fetches`, `fetchMs`, `fetchBytes` |
| Tool calls | number of tool calls in the conversation, all tools |
| Document | the `path` loaded; same as on the other site? |
| Pinpoint | found yes/no (S1, S2, S8, …) |
| Quote | exact yes/no — the quotation matches the page as drawn; both sites' quotations identical apart from documented layout differences (`(77) …` vs `| (77) |`) |
| Fallbacks | other site used, search instead of direct load, read route, retries |
| Errors | error codes and anything that went wrong |

K1 adds: references found (of 10), the altered quotation and the wrong
pinpoint detected (yes/no).

## Decision rule (correctness gate)

1. **Gate.** Count tasks *solved* per site (right document, pinpoint found
   where asked, exact quotation; for S12 and K1, the expected outcome). A
   site is eligible only if it solves at least as many tasks as the other,
   and no task the other solves is failed for a reason the skill cannot
   work around (fallback counts as solved, but is noted).
2. **Tokens.** Among eligible sites, the lower total wins: Cowork usage
   where shown for both, otherwise returned chars + tool calls.
3. **Speed** (total wall time) breaks a tie (within 10 % on tokens).
4. **Outliers.** A task where the sites differ by more than 30 % in tokens
   or wall time is rerun once on both sites; use the mean of the two runs.

The losing site stays the documented fallback. Record the decision and the
date in `docs/lovdata-pro2.md` ("Default site") and change the one line in
SKILL.md Step 0.

## Results

One file per round: `docs/lovdata-pro-default-test-YYYY-MM.md`, a row per
task and site with the fields above, then the decision.
