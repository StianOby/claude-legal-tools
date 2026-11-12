# kildesjekk with subagents: design draft

Status: tried and withdrawn. The Zotero step (§5) was built as a pilot in
kildesjekk 1.7.0 (commit 7e2d69a, 2026-11-11) and taken out again in 1.7.1
(2026-11-12), which restores the 1.6.1 skill. The pilot showed that the
design costs far more than one conversation and catches nothing more on a
manuscript of this size. Read "Pilot results" first; the rest of this file is
the design as it was tried, kept for the record and for a later attempt.

## Pilot results

The manuscript: 84 references (43 footnotes), with 14 planted errors.

| Run | Skill | Outcome |
|---|---|---|
| 1 | 1.6.1, one conversation, through §5 | Finished. 12 of 14 planted errors flagged; one more noticed in a note on a row left for later (the cited page is not in Zotero); one missed (a page one off, where the wrong page also supports the claim) |
| 2 | 1.7.0, Opus retrieval and Opus judging | Stopped by the 5-hour usage limit with 34 of 74 Zotero rows judged and no review done |
| 3 | 1.7.0 as built, Haiku retrieval | Stopped by the same limit with 24 rows retrieved and none judged |

Runs 2 and 3 ran at the same time and shared one usage limit, so neither
shows what one run alone would have reached. The per-row figures still
stand.

**Accuracy.** On the rows run 2 judged, it flagged all ten planted errors
that fell in them, the same ten as run 1. It also flagged seven rows as weak,
uncertain or wrongly pinpointed that run 1 passed. Those were never reviewed; a judge that sees
only a saved passage has less to go on than a reader with the source open.

**Cost.** A retrieval worker used 150,000 to 270,000 tokens for 11 to 13
rows and took about five minutes: about 14,500 tokens per row on Opus, and
15,500 to 22,600 on Haiku. Haiku used more tokens than Opus for the same
work. Six retrieval workers and two or three judges for 74 rows come to
well over a million tokens before the orchestrator's own review. Run 1
did all 84 rows inside one session's limit.

**Why it costs so much**

1. Every worker starts cold: 81,000 to 87,000 tokens of fixed context, the
   instructions, and finding each item again.
2. The passage passes through a model twice: the retrieval worker writes it
   out token by token, and the judge reads it. In one conversation the
   passage is read once and never written.
3. The review step exists only because of point 2, and adds a third read.
4. Large scanned books need several reads to reach a printed page, and each
   worker pays for that again.
5. 40 of the 74 rows cite 8 works. One conversation opens each work once and
   keeps it in context.

**What the pilot did not test.** The reason for the design was a manuscript
of several hundred references, where one conversation fills up and is
compacted. 84 rows did not get there: run 1 finished cleanly, with no
validator violations. Whether workers help at 300 rows is still open.

**If this is tried again**

- Only above a row count where one conversation demonstrably degrades, and
  that count has to be found first.
- One worker per work or group of works, doing the reading and the judging
  together and returning only its results. No copied passages, no separate
  judge, no review of copies.
- The orchestrator passes the Zotero item and attachment keys it already
  has.
- A passage is saved to a file only where a script can write it without a
  model in between (not possible through an MCP tool).
- `quote_check.py` and `worklist.py apply` in commit 7e2d69a worked and
  were tested; they can be taken from there.
- Workers must accept Zotero's cloud route when the desktop app is not
  running. In runs 2 and 3 it was not, and the orchestrators had to override
  `retrieve.md`.

## Why

kildesjekk runs a whole source check in one conversation. A manuscript with a
few hundred references fills that conversation, it gets compacted, and the
rules in SKILL.md fade. The validator, the row invariants and "save every 10
rows" all exist to contain that. Cowork has subagents (confirmed 2026-11-11).
A subagent starts with an empty context, so each batch of references can be
checked by a worker that has just read the rules.

The aims, in order:

1. Fewer silent misses: a green row that should have been flagged.
2. Every `checked = yes` can be audited: the passage the check rested on is
   saved.
3. Shorter wall time where sources can be read in parallel.
4. Lower cost, by giving mechanical work to a cheaper model.

## Roles

| Role | Does | Tools | Model |
|---|---|---|---|
| Orchestrator | Startup, extraction, the worklist, routing rows to workers, user checkpoints, final verification. The only writer of the .xlsx. | All | The session's model |
| Retrieval worker | For a batch of rows from one source route: find the source, find the pinpoint, save the passage. Makes no judgement about the manuscript. | The one source skill or MCP for its route | Haiku |
| Quotation script | Compares each quotation with the saved passage, character by character. | None (Python) | None |
| Judging worker | For a batch of rows: reads the claim, the quotation result and the saved passage, and decides discrepancy, type, severity and description. | File reading only | Opus (maintainer's decision, 2026-11-11) |

The split keeps each worker's instructions short. A retrieval worker needs
one source skill and the "where to look" rules, but not the judgement rules. A
judging worker needs the judgement rules (today's §3), but loads no source
skill and calls no source.

Whether a source supports a claim is always read by Opus. The orchestrator
passes `model: "opus"` for a judging worker and `model: "haiku"` for a
retrieval worker; it never relies on the session's model. Subagents cannot
start subagents, so the orchestrator starts every worker itself.

## Files

All files sit in the session's working directory beside the worklist. None of
them is ever checked into this repo.

- `Kildesjekk_<name>.xlsx`: the worklist, as today.
- `kildesjekk_claims.json`: written by the orchestrator at extraction. One
  record per row with the row key, the **claim** (the sentence or sentences
  of the manuscript that the reference is meant to support) and the resolved
  full reference. The claim is what the judging worker reads in place of the
  manuscript.
- `kildesjekk_batches/<batch>.json`: written by `worklist.py batch`. The rows
  of a batch with reference and quotation (from the worklist), claim (from
  the claims file) and the path of each row's evidence file. It is the only
  thing a worker is handed.
- `kildesjekk_evidence/<key>-<hash>.txt`: one per row, written by a
  retrieval worker.
- `kildesjekk_quotes/<batch>.json`: written by `quote_check.py`.
- `kildesjekk_results/<batch>.json`: written by a judging worker.

An evidence file is plain text: field lines, then a `--- passage ---` line,
then the passage. Plain text, so that a worker copies the passage without
escaping anything, and so that the user can open the file and read it.

| Field | Content |
|---|---|
| `key` | The row key |
| `outcome` | `found`, `not_here` (not in this route; a later step may find it) or `unavailable` |
| `source` | What was opened: Zotero item key, CELEX, URL, itemid |
| `route` | The skill or MCP used |
| `locator` | Where the passage is, in the source's printed pagination or paragraph numbers |
| `pinpoint_matches` | `yes`, `no` (found elsewhere; `locator` says where) or `none` (no pinpoint cited) |
| `emphasis_known` | `no` for PDF and OCR text, which carry no emphasis |
| `tools_tried` | The searches and reads made |
| `note` | The record's own details (author, title, edition, year), and anything the judge should know, e.g. "OCR text" |

A retrieval worker that cannot open the original source never fills the
passage from another work that cites the source.

## Flow of one step

1. The orchestrator picks the rows with `checked = no` that belong to the
   step, and groups them by source so that each book or judgment is opened
   once. A retrieval batch is 10 to 15 rows, or fewer when they span many
   sources. A judging batch is larger, 30 to 40 rows, since a judging worker
   makes no source calls (see "Cost of a worker").
2. It starts retrieval workers, as many at a time as the route allows (table
   below). Each gets its batch from `kildesjekk_rows.json` and the path of
   one reference file with its instructions.
3. When a batch's evidence is written, the orchestrator runs the quotation
   script on it.
4. It starts a judging worker when 30 to 40 rows have evidence, or when the
   step has no more rows.
5. It applies the results file with `worklist.py apply`, which writes values
   and colours and runs the validator. Rows with `not_here` stay at
   `checked = no` for a later step.
6. The orchestrator itself reads every row the judge flagged against the
   evidence, and reads quotation and page findings and a sample of the clean
   rows at the source, before the step is reported as done.
7. It stops and asks the user before the next step, as today.

## Cost of a worker

Every subagent in the probe used 81,000 to 87,000 tokens before doing any
work, whatever its model: its system prompt and tool list. So workers are not
free, and the design keeps their number down:

- Batches are as large as a worker's context allows. Retrieval workers read
  with `query` and narrow page ranges, never whole documents.
- A manuscript with fewer than about 30 references is checked without
  subagents: the main conversation plays each role in turn. The pilot should
  show where the break-even point is.
- A step with only a few rows of a kind (two ICJ cases, one EFTA Court case)
  goes to one retrieval worker per route, never one per row.

For 300 references this gives roughly 25 retrieval workers and 10 judging
workers: about 2 million tokens of fixed cost on Haiku and under 1 million on
Opus. The probe does not show how those tokens are billed (cached or not).
The pilot measures the real cost against today's single conversation.

## How many workers at a time

The rule: one worker per source route at a time, except Zotero.

| Step | Route | At a time | Why |
|---|---|---|---|
| §4 internal cross-references | The manuscript | 1 judging worker, or the orchestrator | No source to fetch |
| §5 Zotero, and the Zotero part of §§7–8 | zoteus MCP | 3 to start with | MCP calls only; the limit is untested |
| §6 statutes | lovdata-api, local shell | 1 | Lookups are instant; one local shell |
| §§7–8 lovdata-pro | Browser pane | 1 | One pane |
| §9 EU law | eurlex MCP | 2 | Its search already times out now and then |
| §10 eea-lex, §11 efta-court, §12 ets and untc | `Bash` scripts | 1 per skill, the four side by side | Different hosts; one polite client per host |
| §12 norges-traktater, eu-agreements-treaties | Browser pane | 1 | One pane |
| §13 ICJ | Browser pane for the PDFs | 1 | One pane |
| §14 HUDOC | Script, browser fallback | 1 | Challenges are per client; more requests make them worse |
| §15 nbno | Local shell, OCR | 1 | About 2 vCPUs |

All browser-pane routes share one pane, so at most one browser worker runs at
any time, across steps.

## The quotation script

`scripts/quote_check.py <batch file>` compares each row's quotation with its
evidence passage and reports one of:

- `exact`: the quotation is in the passage, character for character.
- `marks_only`: it is there once all quotation marks are treated as alike.
- `differs`: the nearest match in the passage, with each difference listed.
- `not_in_passage`: no near match.

It treats a quotation with ellipses as parts that must occur in order, lists
bracketed insertions for the judge to assess, does not accept a match that
starts or ends inside a longer word, and compares emphasis markers only when
`emphasis_known` is yes. It counts runs of whitespace and non-breaking spaces
as one space and ignores soft hyphens; it tolerates nothing else. The script
gives no verdict on severity. That stays with the judging worker, who may not
overrule the script's reading of the wording.

## A known weakness: the passage is copied by a model

A script-based skill can write a source's text straight to a file. An MCP
tool cannot: what Zotero returns reaches the evidence file only through the
retrieval worker, which copies it. A copying slip then looks like a
misquotation, and a worker that "corrects" the passage towards the
manuscript's quotation would hide a real one. Three things limit this:

- `retrieve.md` tells the worker to copy and never correct, and why.
- The orchestrator reads every quotation finding, every wrong-page finding
  and every "Assessment uncertain" at the source itself before it stands.
- It also reads one in ten of the clean rows with a quotation at the source.

The pilot shows whether this is enough: planted quotation errors that a
Haiku retrieval run misses, and false quotation findings it produces. If it
is not, the options are a stronger retrieval model or, for sources a script
can fetch, writing the passage to the file without a model in between.

## Rules that carry over unchanged

- Only the original source counts, in the edition cited.
- Only the tools SKILL.md names, and no web search.
- A Cloudflare challenge, a 405 or a geo 403 is not a missing source.
- The row invariants and the validator.
- The step order and the user checkpoint after each step.

## Failures

- A worker that fails or returns nothing: its rows stay at `checked = no`.
  The orchestrator retries the batch once, then reports it to the user. It
  does not check the rows itself as a quiet fallback.
- A results file with a row key that is not in the batch, or with a row
  missing: `apply` refuses the whole file.
- An evidence record with `found` but an empty `passage`: treated as a failed
  row.

## As built (the §5 pilot, kildesjekk 1.7.0; removed in 1.7.1)

- `scripts/quote_check.py`: the quotation script and the evidence-file
  reader. Standard library only.
- `scripts/worklist.py`: new commands `batch` and `apply`. `apply` refuses a
  results file as a whole if a row is missing or added, if a row breaks an
  invariant, if `checked` does not fit the evidence outcome (`yes` needs
  `found`), if a row is already checked, or if the script found a quotation
  difference and the row has no discrepancy and no description.
- `references/retrieve.md` and `references/judge.md`: the two roles.
  `references/zotero.md`: the how-to for Zoteus, moved out of SKILL.md §5.
- SKILL.md: the claims file (§2) and a new §5. Workers are used when the
  `Agent` tool is there and the step covers 30 rows or more; otherwise the
  main conversation does the same parts itself.
- `tests/kildesjekk/test_quote_check.py`, `test_apply.py`.

Where the pilot stops short of the design:

- The judgement rules (SKILL.md §3) stay in SKILL.md, since §§6–16 still use
  them in the main conversation. The judging worker is pointed to those
  sections. At rollout they move to `references/judge.md`.
- Retrieval batches and judging batches are the same batch files; a judging
  worker takes up to three of them.
- §§4 and 6–16 are unchanged: the main conversation checks those rows and
  writes them to the worklist as before.

## Pilot

§5 only, since it is the largest step, uses only MCP calls and needs no
browser. One manuscript is run three ways, each in a fresh Cowork session,
through §5 and no further:

1. kildesjekk 1.6.1 (before this change), in one conversation.
2. kildesjekk 1.7.0, told to use Opus for the retrieval workers too.
3. kildesjekk 1.7.0 as built: Haiku retrieval, Opus judging.

The manuscript is a slice of a book chapter by the maintainer: 43 footnotes,
with 14 planted errors (six changed quotations, four wrong pages, two changed
claims, two wrong citation details). The slice and its answer key are kept
outside this repo. No emphasis error is planted, since the Zotero step reads
PDF text.

Measure: planted errors caught (counting only rows whose source is in Zotero
with full text), false flags, tokens per model, wall time, and validator
violations along the way.

Roll the design out to the other steps only if run 2 or 3 catches at least as
many planted errors as run 1. At rollout the worker instructions leave §5:
SKILL.md gets one general section on batches, workers, applying and review,
each step names its route and how many workers it may run, and
`retrieve.md` gets a part per source route.

## Probe

Run in cloud Cowork on 2026-11-11, with the session on Opus 5.5. Every
question the design depended on came out as yes.

| Question | Result |
|---|---|
| The subagent tool | `Agent`, in the tool list from the start. Parameters include `model` (`sonnet`, `opus`, `haiku`, `fable`), `effort`, `subagent_type` and `run_in_background` (default true) |
| Model choice | Works: `haiku` gave Haiku 5.5, `opus` gave Opus 5.5. With no `model`, the subagent gets the session's model |
| MCP tools from a subagent | zoteus and eurlex both found and working (`zotero_whoami`, `eurlex_metadata`) |
| Skills from a subagent | All visible; the efta-court skill loaded and its script ran |
| Shared files | Yes: same host, and files under `/mnt/user-data/outputs/` are seen both ways |
| Browser pane from a subagent | Reachable (`tabs_context`). It is the same single pane for every subagent |
| Local shell from a subagent | `device_bash` works |
| Nested subagents | No: a subagent has no `Agent` tool |
| Running at the same time | Yes: three subagents overlapped fully, each with a Zotero search |
| Fixed cost | 81,000 to 87,000 tokens per subagent, also for one that only ran `echo ok` |

What the results changed in this design:

- The fixed cost led to larger batches and a floor of about 30 references
  ("Cost of a worker").
- The shared pane confirms the rule of one browser worker at a time. The
  probe's own note: parallel browser work could collide over the tab.
- No fallback is needed for evidence files, model choice or parallel runs.

## Decisions made

All by the maintainer, 2026-11-11.

- **Lovdata Pro text in evidence files.** Saving selected passages in the
  session's working directory is fine. Evidence files hold the passage a
  check rests on, never whole documents.
- **Without subagents.** The main conversation plays each role in turn from
  the same reference files, so there is one set of instructions. The skill
  does not require subagents.
- **The judging model.** Opus (see "Roles").
- **The pilot manuscript.** A slice of a chapter the maintainer supplied.
