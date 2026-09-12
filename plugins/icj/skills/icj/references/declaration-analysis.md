# Comparing two declarations — worked example

This file shows how to use the skill to answer the kind of question the
user asked us to support: *"Would Norway's and Finland's declarations
allow an ICJ case concerning a territorial dispute between them?"*

## Step 1 — Confirm both states have an active declaration

```bash
python scripts/icj.py declarations list | grep -Ei "norway|finland"
```

Both Norway and Finland appear with deposit dates (Norway 24 June 1996,
Finland 25 June 1958 as of writing).

If either state were absent, the optional clause is unavailable and the
analysis would have to look at jurisdictional treaties between the parties
(`jurisdiction treaties`) or whether they could conclude a special
agreement.

## Step 2 — Pull both texts side by side

```bash
python scripts/icj.py declarations compare no fi
```

Read both declarations carefully. Note in particular:

- The declaration's *date of force* and any duration / termination
  clauses.
- All reservations. List them out before applying any to the dispute.

## Step 3 — Apply reciprocity

Article 36(2) operates on a reciprocal basis. Under the *Norwegian Loans*
case (France v. Norway, 1957), a respondent state may invoke a reservation
in the *applicant's* declaration as well as its own. So the Court has
jurisdiction only if the dispute is *outside every reservation in either
declaration*.

When you draft the analysis, walk through each reservation in each
declaration and ask: does this reservation exclude the dispute at hand?
If any reservation in *either* declaration excludes the dispute,
compulsory jurisdiction under the optional clause is unavailable.

## Step 4 — Map reservations to a territorial dispute

For a hypothetical Norway–Finland territorial dispute, the relevant
reservations would typically be:

- **Other-method-of-settlement reservations.** If the parties have a
  bilateral or regional settlement mechanism that covers boundary
  questions, that may exclude ICJ jurisdiction. (Norway and Finland are
  both parties to the European Convention for the Peaceful Settlement of
  Disputes (ETS 23) and to UNCLOS for maritime boundaries.)
- **Norway's UNCLOS carve-out.** Norway's declaration excludes "all
  disputes concerning the law of the sea" insofar as those disputes are
  subject to UNCLOS Part XV. A pure land-territory dispute is not covered
  by this carve-out; a maritime delimitation dispute is.
- **Time-bar reservations.** Both declarations should be checked for any
  reservation excluding disputes arising before a particular date or
  involving facts before a particular date.
- **Subject-matter exclusions.** Read each declaration in full — sometimes
  there are state-specific carve-outs (defence, internal affairs).

## Step 5 — Conclude

Three possibilities:

1. **The dispute fits within both declarations and reciprocity is
   satisfied** → the ICJ has compulsory jurisdiction under Article 36(2),
   and either party may file a unilateral application.
2. **A reservation in either declaration carves the dispute out** →
   compulsory jurisdiction unavailable; the parties would need to
   conclude a special agreement under Article 36(1), or rely on a
   compromissory clause in a treaty in force between them.
3. **Doubt** → jurisdictional disputes go to the Court itself under
   Article 36(6); but for advice, flag the relevant reservation and
   recommend that the parties consider a special agreement to avoid
   protracted preliminary objections.

## Always quote, never paraphrase

Reservations are interpreted as written. When you summarise an answer for
the user, quote the actual reservation language from `declarations show`.
Paraphrasing risks understating or overstating the carve-out. The cached
text is the canonical English version published by the Court.

## Where the analysis fails

The optional clause is only one of four jurisdictional bases (see
`jurisdiction-overview.md`). If the declaration analysis closes the door,
do not stop — check:

- Whether the parties are both parties to a multilateral treaty with a
  compromissory clause covering the dispute (genocide, racial
  discrimination, torture conventions all have such clauses; numerous
  bilateral treaties do too).
- Whether they could conclude a special agreement.
- Whether either party has consented (or can be argued to have consented)
  by conduct (forum prorogatum).
