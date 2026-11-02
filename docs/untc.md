# untc — what a UNTS registration holds

Why `untc.py text` cuts a registration down to the registration note and one
language, and what the survey behind that found (2026-11-02).

## The parts of a registration

A treaty is printed in a UNTS volume under its registration number. Cutting
from that number to the next (a volume cut), or downloading the UN's
per-treaty file, brings along everything below. Neither kind of file holds
only the treaty text.

| Part | Content | Kept by default |
|---|---|---|
| Registration note | Title, place and date, entry into force, authentic languages, date and mode of registration. English and French, one page. | yes |
| Parties at registration | The states bound on the day of registration (a footnote in older volumes). A snapshot: CRPD, 20 states as of 3 May 2008. | no |
| Reservations and declarations | Those made by the first parties, at signature or at ratification. Original language plus the Secretariat's `[TRANSLATION – TRADUCTION]`. Also a snapshot; the MTDSG status doc has all of them. | no |
| Authentic texts | One block per language. Newer volumes open each with `[ENGLISH TEXT – TEXTE ANGLAIS]` (from about vol. 3100 `[ TEXT IN ENGLISH – TEXTE EN ANGLAIS ]`). Older ones leave English and French unmarked, or print the marker bare (`No. 3237. JAPANESE TEXT - TEXTE JAPONAIS`). Arabic, Hebrew and old Japanese are bound right to left, so the marker sits on the last page of the block. | the `--lang` one |
| Other instruments under the same number | Separate instruments with their own texts, e.g. the ICCPR and its Optional Protocol (both No. 14668). | yes, in the `--lang` language |
| Signatures | Facsimile pages ("FOR AFGHANISTAN: / POUR L'AFGHANISTAN:"), up to ~26 per instrument; a list of signatories in newer volumes. | no |
| Secretariat translations | Where English or French is not authentic (most bilaterals): `[TRANSLATION]` into English and `[TRADUCTION]` into French. Older volumes print them on the pages facing the authentic text. | the English one, with the authentic texts, when English is not authentic |

The maintainer's choices (2026-11-02): by default keep the registration note,
the English text, and other instruments under the same number. Drop the
parties, reservations and signatures printed at registration. Where English
is not authentic, keep the authentic texts plus the English translation. Trim
both the text Claude reads and the PDF (Zotero included). `--lang` picks
another language (`fr`, `ar`, `zh`, `ru`, `es`, or a name such as
`norwegian`), and `--full` gives the whole registration. For `ar`/`zh`/`ru`/`es`
and other languages, a per-treaty "Other" file is cut to that language.

Examples: the CRPD (vol. 2515, cut from the volume) runs to 190 pages, 27 of
them English. The ICCPR's per-treaty "English" file (vol. 999) has 92 pages:
the note, the Covenant, 26 pages of signatures, 20 of reservations, the
Optional Protocol, 25 more of signatures and the ratification reservations.
The Rome Statute's English file (vol. 2187) is clean.

## The UNTS record

`text` first looks the treaty up in UNTS Online by registration number
(the advanced search: Treaty → Registration Number, four ASP.NET
postbacks, about 4 s; a fresh session per lookup, because a reused one was
reset by the server) and reads its record (`showDetails.aspx`). Cached as
`record.json` for 7 days. It supplies, without OCR:

- **Authentic texts**, which decide authentic text against translation.
  The registration note's line is the fallback; most notes before about
  vol. 700 have none.
- **Publication format**: Full, Partial Publication (parts, often annexes,
  left out) or Limited Publication (only the registration note printed).
- **Text document(s)**: the per-treaty files (English/French/Other) for
  older volumes; the registration's own file `Volume N/Part/volume-N-I-…`
  for recent ones (all languages, volume pagination, far smaller than the
  volume); and `No Volume/…/Part/I-…` before the volume is published,
  with its own page numbers. These are the same scans as the volume: they
  do not fix the missing text layer.
- **Related records**: `A-` entries under the same number (protocols,
  amendments, corrections).
- **Participants** (`unts-details --participants`): the actions
  registered with the UN. Not a status list: an action appears only once
  someone registers it, and the table has no reservations. The output
  and SKILL.md carry a caveat that goes to the user every time.

Without the record (site unreachable, no record) `text` works from the
PDF alone, as before, and says so in `record_error`.

## How the pages are told apart

`label_pages()` reads a registration page by page. Headings start a part:
"Participant Ratification", "DECLARATIONS AND RESERVATIONS", "Reservation made
upon …", "LIST OF SIGNATORIES", or FOR/POUR facsimile lines. Language markers
start a text, and stopwords tell unmarked pages apart (English, French,
Spanish, Dutch, German; "mixed" for two columns). A page with no text layer
takes the label of the page before it.

Two rules decide whether a page is authentic or a translation:

- **Inside a reservations section,** only a marker that opens a page ends
  the section, because reservations quote originals under markers mid-page.
  In older volumes an unmarked page of treaty text (a line starting
  "Article") ends it too.
- **On facing pages,** the registration note's "Authentic texts" line
  decides. Where it is missing (before about vol. 700), a language that has
  had a translation marker counts as translation.

If the asked-for text cannot be found, the whole registration is kept and the
output says so. `tests/untc/test_parts.py` holds fixtures for each pattern.

## Survey (2026-11-02)

Six registrations per volume: vols. 8, 30, 100, 138, 158, 188, 232, 348, 400,
700, 703, 788, 848, 1000, 1137, 1200, 1233, 1373, 1400, then every 100 to
3200. Vols. 1 and 2500 could not be sampled (no contents parsed). Vols. 3300
and later were not yet published as PDFs.

- **Scanned texts.** Up to vol. 2300, the English text had a text layer in
  every sample (OCR in the early volumes). From vol. 2400 the English text
  is a scan whose text layer holds only the running head and the language
  marker: 1 of 3 sampled in vol. 2400, then every sample from vol. 2600 to
  3200 (29 of 29). The CRPD (vol. 2515) is one. `text` names those pages in
  a `warning`, and Claude has to read them as images. OCR would be the next
  step if this is to change. See **Why the newer texts are scans** below.
- **Per-treaty files** (`volume-N-I-…-English.pdf` etc.). Present for
  nearly every sample up to vol. 1500, and for none from vol. 1600. Recent
  volumes have the registration's own file under `Volume N/Part/` instead
  (seen in vols. 3000 and 3200). The survey only probed the old names; the
  UNTS record lists whichever exists, and `text` takes it from there.
- **Not printed.** Many registrations from about vol. 1400 on are only a
  registration note: "Not published herein in accordance with article 12(2)"
  of the GA regulations. Older ones were printed as a title only,
  "Publication effected in accordance with article 12(2)". `text` reports
  `not_published` for these.
- **Running heads.** From about vol. 2400 the head reads "Volume 2515,
  I-44910" with the folio on the next line. `printed_page_of` did not read
  it before 1.6.0, so `printed_pages` came back empty for every newer
  volume.

## Why the newer texts are scans

The UN's own wording, in the "Note by the Secretariat" at the front of
every volume from about vol. 2400:

> Disclaimer: All authentic texts in the present Series are published as
> submitted for registration by a party to the instrument. Unless
> otherwise indicated, the translations of these texts have been made by
> the Secretariat of the United Nations, for information.

So the scan is the copy the party sent; only the registration note, the
running heads and the language markers are typeset, and that is all the
text layer holds. Front matter checked (2026-11-02): vols. 2300 (printed
2007), 2340 (2006), 2370 (2007) and 2390 (2010) have no disclaimer; vols.
2400 (2010), 2450 (2010) and 2515 (2011) have it. The date that matters is
the printing, not the registration: the CRPD was registered in 2008 and
printed in 2011.

Before that, the Secretariat retyped the texts: the Legal Counsel's notes
on registration (2003, 2008, 2010) ask for a paper copy "machine readable
and legible for use by the optical character recognition mechanism
employed in the desktop publishing process". The Repertory of Practice,
Art. 102, Suppl. 9 (1995–1999), § 7, describes the workflow system begun
in 1997.

No source found states why the practice changed. The likely reason is the
publication backlog (eleven years in 1996; GA resolution 73/210 of 2018
still notes "a significant backlog in the publication of the United
Nations Treaty Series"): reproducing the submitted copy skips typesetting
and proofreading. One consequence: OCR by the skill would be the first
transcription of these texts anyone has made, and must be marked as such.
