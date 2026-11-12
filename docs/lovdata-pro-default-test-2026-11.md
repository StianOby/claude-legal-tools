# lovdata-pro default-site test, round 1 (2026-11-12)

Protocol: `docs/lovdata-pro-default-test.md`. lovdata-pro 1.3.1, cloud
Cowork, one fresh subagent per run (orchestrator prompt), runs strictly one
at a time. 30 runs, 15 tasks × 2 sites. Two first attempts (run 13, S7
Klassisk; run 25, K1 Klassisk) stopped at the 5-hour usage limit and were
rerun fresh; the reruns are counted. The raw RESULTAT blocks are kept by the
maintainer; they hold no document text.

K = Klassisk (`lovdata.no/pro/?forceFullVersion=true`), P = new Lovdata Pro
(`pro2.lovdata.no`). Tokens = the subagent's token figure as the
orchestrator's tool reported it. Chars = `__lp.stats().returnedChars`.

| Task | K tokens | P tokens | K wall s | P wall s | K tool calls | P tool calls | K chars | P chars | Solved K / P |
|---|---|---|---|---|---|---|---|---|---|
| S1 HR para | 149,630 | 157,732 | 137 | 144 | 13 | 14 | 6,307 | 6,194 | yes / yes |
| S2 Rt. + page | 154,721 | 154,674 | 157 | 156 | 14 | 14 | 8,094 | 6,399 | yes / yes¹ |
| S3 RG | 154,085 | 157,463 | 149 | 154 | 13 | 13 | 10,806 | 5,876 | yes / yes¹ |
| S4 LB | 150,913 | 152,485 | 142 | 149 | 12 | 11 | 5,004 | 4,979 | yes / yes |
| S5 TOSL | 154,858 | 154,329 | 168 | 151 | 14 | 14 | 11,628 | 10,183 | yes / yes |
| S6 metadata | 147,949 | 149,593 | 138 | 132 | 11 | 11 | 2,073 | 2,011 | yes / yes |
| S7 NOU large | 152,075 | 151,092 | 143 | 149 | 13 | 13 | 76,177 | 76,229 | yes¹ / yes |
| S8 NOU old | 151,377 | 148,220 | 151 | 155 | 14 | 13 | 47,327 | 88,795 | yes / yes¹ |
| S9 Ot.prp. | 154,173 | 149,487 | 164 | 141 | 13 | 12 | 48,083 | 47,914 | yes / yes¹ |
| S10 Prop. L | 150,001 | 148,952 | 145 | 144 | 13 | 11 | 29,691 | 34,209 | yes / yes |
| S11 Innst. | 153,520 | 164,595 | 184 | 178 | 13 | 13 | 32,325 | 36,147 | yes² / yes |
| S12 Meld. St. | 150,740 | 161,398 | 188 | 255 | 18 | 12 | 972 | 1,019 | yes³ / yes³ |
| K1 kildesjekk | 232,917 | 232,188 | 407 | 405 | 46 | 45 | 176,436 | 221,989 | yes / yes⁴ |
| T1 topic | 170,279 | 180,830 | 212 | 212 | 17 | 18 | 55,520 | 82,528 | yes / yes |
| F1 forarbeider | 169,423 | 169,109 | 227 | 190 | 21 | 16 | 137,180 | 141,344 | yes / yes¹ |
| **Total** | **2,396,661** | **2,432,147** | **2,712** | **2,715** | **245** | **230** | **647,623** | **765,816** | **15 / 15** |

P against K: tokens +1.5 %, wall time +0.1 %, tool calls −6.1 %, returned
chars +18.3 %. All 30 runs together: 4.83 M tokens.

1. Quotation checked against the helper's text only: the pane drew the
   page blank or partly when the run checked it afterwards (a pane that is
   not being painted does not render; see "Notes"). Round 0 had compared the
   new Pro's text with the drawn page and found them identical.
2. Correct, but Klassisk glued a page marker into a sentence ("fraSide 39",
   `span.side`): fixed in 1.3.2.
3. Expected outcome: neither site has the text of Meld. St. 17 (2020-2021).
   P fell back to Klassisk (`missing_json`), which has a metadata-only
   record. The K run also met a `search_timeout` (1.3.2 reports an empty
   result page as `noHits`).
4. Both K1 runs found 10 of 10 references, the altered quotation (fn. 6)
   and the wrong pinpoint (fn. 7).

## Decision rule

1. **Gate:** 15 / 15 on both sites, with the same S12 outcome. Both
   eligible.
2. **Tokens:** +1.5 % for P, within 10 %: a tie.
3. **Speed:** +0.1 % wall time (−0.7 % subagent duration): a tie.
4. **Outliers (> 30 %):** S11 (duration +37 %; the P agent used 29 tools
   against 14, run-to-run variation) and S12 (wall time +36 %; the designed
   fallback to Klassisk). **Not rerun** (maintainer, 2026-11-12): two
   reruns on both sites cost about 600 k tokens and cannot change a tie
   within 10 % on total tokens.

The measurement cannot separate the sites. About 150 k of every run's
tokens are fixed subagent context; the site-dependent part varies by a few
per cent. Where the same document is read the same way, both sites return
almost the same characters (S7 76,177 / 76,229; S9 48,083 / 47,914): one
text converter. The large differences in returned chars (S8, T1, K1) are
agent choices (reading a whole section instead of grepping, opening 8
judgments instead of 4, reading in Zotero instead of Lovdata), not the
site. Network time is 0.05–1.9 s per task on both, against 130–400 s of
wall time.

## Decision (maintainer, 2026-11-12)

**The new Lovdata Pro becomes the default when it launches**, with Klassisk
as the fallback: the switch is made after 2026-11-26, once the new Pro's
final state (address, API) is known — see "Switchover" in
`docs/lovdata-pro2.md`. Until then SKILL.md keeps Klassisk.

Reasons beyond the measured tie: the new Pro is where logins land from
2026-11-26 and the only site after 2027; on it, search is one API call
(Klassisk's synthetic key press timed out in S12), Rt./RG resolve directly
(Klassisk needed a search in S2/S3), and the user's search history is left
alone. Its risk, an undocumented API that may change, is contained by the
`unsupported_format` error and the Klassisk fallback.

## Notes for the next round

- **Cost:** 30 subagent runs used 4.83 M tokens and hit the 5-hour limit
  twice. Next time, run fewer tasks (one per kind), or separate
  conversations over several limit windows; never parallel sessions.
- **S12** tests nothing useful: stortingsmeldinger are not meant to be in
  Lovdata (maintainer, 2026-11-12). Replace it, e.g. with an Innst. O. or
  an old Ot.prp.
- **Checking against the drawn page:** the pane only renders while it is
  painted. Have the run take a screenshot (or bring the pane forward) before
  `get_page_text`, or drop the check where Round 0 already covers it.
