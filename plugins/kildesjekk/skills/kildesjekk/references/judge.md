# Judging: decide what each row says

You are doing the judging part of a source check (kildesjekk) of an academic legal text. For each row of a batch, someone has already found the cited source and saved the passage, and a script has compared any quotation with it. You read the claim, the passage and the script's result, and decide what goes into the worklist.

You call no source. You use no tool other than reading the files named here and writing the results file. If the saved passage is not enough to decide a row, do not guess and do not look the source up: follow "When the passage is not enough" below.

## Read first

The skill's `SKILL.md` (its path is in your instructions). Read these parts only:

- In section 2: "The 'type of discrepancy' column" and "The 'description' column".
- In section 3: "Correspondence rules" and "Flagging".

They are the rules you judge by. The rest of that file is for someone else.

## What you are given

For each batch, a batch file (JSON) with:

- `rows`: each with `key`, `reference`, `full_reference`, `quoted`, `claim` and `evidence_file`.
- `quotes_file`: the script's result for each row.
- `results_file`: where you write your result.

An evidence file has field lines (`outcome`, `source`, `locator`, `pinpoint_matches`, `emphasis_known`, `tools_tried`, `note`) and then, after the `--- passage ---` line, the passage copied from the source.

A row in the quotes file has a `verdict`:

| Verdict | Meaning |
|---|---|
| `exact` | The quotation is in the passage, character for character |
| `marks_only` | It is there once all quotation marks are treated as alike |
| `differs` | A near match was found; `differences` lists each place, with the quotation's words and the source's |
| `not_in_passage` | Nothing like the quotation is in the passage |
| `no_quotation` | The row has no quotation |
| `no_passage` | The source was not read |

It also gives `insertions` (bracketed text in the quotation), `omissions` (the number of ellipses), `emphasis` (`same`, `differs` or `not_compared`) and `source_text` (the matching stretch of the source).

## For each row

Start from the evidence file's `outcome`:

- **`not_here`:** the row is left for a later step. Result: `checked` = `no`, every other field empty.
- **`unavailable`:** `checked` = `source unavailable`; `description` says which tools were tried (from `tools_tried`); the other fields empty.
- **`found`:** `checked` = `yes`. Go through the four points below.

1. **Is it the work cited?** Compare the reference with the record in `note` (author, title, year, edition, volume, case number). A mismatch is a "Citation format error". A later reprint of the cited edition is not a mismatch. For a bibliography entry, compare every detail of the entry with the title page in the passage.
2. **Is the pinpoint right?** If `pinpoint_matches` is `no`, it is "Wrong page/section/paragraph", and the description gives the place in `locator`.
3. **Is the quotation verbatim?** Take the wording from the script's verdict:
   - `exact`: the wording is right. Check against the passage that each insertion reflects what it replaces, and that no ellipsis changes the sense.
   - `marks_only`: a difference in quotation marks only. Low severity where it concerns a quotation within the quotation.
   - `differs`: "Quotation not verbatim", normally high. In the description, name each difference and give the source's wording from `source_text`.
   - `not_in_passage`: the quotation is not at the place cited. "Quotation not verbatim" or "Wrong page/section/paragraph", normally high; say that the words were not found there.
   - `emphasis` = `differs`: "Quotation not verbatim", normally medium, unless the manuscript flags the change ("emphasis added", "min uthevelse") and the flag matches it.
   - `emphasis` = `not_compared`, and the quotation has `*` markers: say in the description that emphasis could not be compared.
4. **Does the passage support the claim?** Read the claim and the passage and judge as the "Correspondence rules" set out: obvious discrepancy, weak support, or uncertain.

Where a row has several discrepancies, the most severe decides `type` and `severity`, and the description names them all.

Two limits on point 3:

- **Do not overrule the script by your own reading of the wording.** If you think its verdict is wrong, keep the row as a finding with the type "Assessment uncertain" and say why.
- **Scanned text.** If `note` says the text is scanned or OCR, a difference that a misreading could explain (ligatures, `rn` for `m`, a lost diacritic, hyphenation at a line break, one kind of dash for another) is not a finding on its own. Set `discrepancy` = `no` and say in the description what the difference is and that the user should look at the page. A changed, added or missing word is still a finding.

## When the passage is not enough

If the passage does not cover what the claim is about, or is too garbled to read, you cannot tell whether the source supports the claim. Then: `discrepancy` = `yes`, `type` = "Assessment uncertain", `severity` = `medium`, and a description that begins "The saved passage does not settle this:" and says what is missing. The orchestrator reads every such row against the source again.

Never mark a row `no` discrepancy because you could not tell.

## The results file

For each batch, write its `results_file` as JSON, one object per row of the batch, none missing and none added:

```json
{
  "rows": [
    {"key": "14a", "checked": "yes", "discrepancy": "no", "type": "", "severity": "",
     "description": "", "source": "Zotero ABCD1234, p. 211"},
    {"key": "14b", "checked": "yes", "discrepancy": "yes",
     "type": "Wrong page/section/paragraph", "severity": "low",
     "description": "The passage cited is at p. 212, not p. 211.",
     "source": "Zotero ABCD1234, p. 212"},
    {"key": "15", "checked": "no", "discrepancy": "", "type": "", "severity": "",
     "description": "", "source": ""}
  ]
}
```

| Field | Content |
|---|---|
| `key` | Exactly as in the batch file |
| `checked` | `yes`, `no` or `source unavailable`, as the outcome dictates |
| `discrepancy` | `yes` or `no` when `checked` is `yes`; otherwise empty |
| `type` | A label from SKILL.md's list when `discrepancy` is `yes`; otherwise empty |
| `severity` | `high`, `medium` or `low` when `discrepancy` is `yes`; otherwise empty |
| `description` | 1–3 sentences. Required for a finding, for `source unavailable`, and for a row where the script found a difference that you do not treat as a finding |
| `source` | The evidence file's `source` and `locator`, when `checked` is `yes` |

Page numbers in descriptions are the printed ones in `locator`.

## When you are done

End with one line per batch: how many rows are `yes`, `no` and `source unavailable`, and how many findings by severity. Do not repeat the descriptions.
