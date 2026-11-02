#!/usr/bin/env python3
"""Regression tests for telling the parts of a UNTS registration apart and
keeping the registration note and the English text.

No network: the fixtures follow the page text pypdf extracts from the volumes
named below, with the body text cut to a sentence or two in the right
language.

Run with `python tests/untc/test_parts.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "plugins" / "untc" / "skills" / "untc" / "scripts"))

import untc  # noqa: E402

failures = []


def check(name, got, want):
    if got == want:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s: got %r, want %r" % (name, got, want))
        failures.append(name)


EN = ("Each State Party shall take all appropriate measures to ensure that the rights of "
      "persons with disabilities are protected by law, and that any such measure shall be "
      "applied with due regard to the provisions of this Convention and of its annex.\n")
FR = ("Les Etats Parties prennent toutes les mesures appropriees pour que les droits des "
      "personnes handicapees soient garantis par la loi, et que les mesures prises dans le "
      "cadre de la presente Convention et de ses annexes soient appliquees sur leur territoire.\n")
DE = ("Die Vertragsparteien treffen alle geeigneten Massnahmen, um sicherzustellen, dass "
      "die Rechte der Menschen geschuetzt werden, und wenden diese Bestimmungen an.\n")


def modern(n, body=""):
    """A page with the running head of the newer volumes (vol. 2515)."""
    return "Volume 2515, I-44910 \n %d\n%s" % (n, body)


def old(n, body=""):
    """A page with the running head of the older volumes (vol. 999)."""
    return "%d United Nations - Treaty Series * Nations Unies - Recueil des Traites 1976\n%s" % (n, body)


def kinds(labels):
    return [untc.describe_label(l) for l in labels]


# --------------------------------------------------------------------------
# CRPD, vol. 2515, No. 44910 (cut from the volume PDF): parties and
# reservations as at registration, six languages - all of them scans whose
# text layer holds only the running head and the language marker - and the
# list of signatories. Arabic is bound right to left, so its marker sits on
# the last page of its block.
# --------------------------------------------------------------------------
print("CRPD (vol. 2515)")
CRPD = [
    modern(3, "No. 44910 \n____ \nMultilateral \nConvention on the Rights of Persons with "
              "Disabilities. New York, 13 December 2006 \nEntry into force:  3 May 2008 \n"
              "Authentic texts:  Arabic, Chinese, English, French, Russian and Spanish \n"
              "Registration with the Secretariat of the United Nations:  ex officio, 3 May 2008 \n"),
    modern(4, " \nParticipant Ratification \nBangladesh   30 Nov  2007 \nCroatia   15 Aug  2007 \n"),
    modern(5, " \nParticipant Ratification \nAfrique du Sud   30 nov   2007 \n"),
    modern(6, " \nReservation made upon Ratification Reserve faite lors de la Ratification \n"
              "EL SALVADOR EL SALVADOR\n \n[ SPANISH TEXT - TEXTE ESPAGNOL ] \n \n"
              "[TRANSLATION - TRADUCTION] \n" + EN + "[TRANSLATION - TRADUCTION] \n" + FR),
    modern(7, " \nInterpretative declaration made upon    \nRatification \nMEXICO MEXIQUE\n"
              " \n[ SPANISH TEXT - TEXTE ESPAGNOL ] \n"),
    modern(8, "[TRANSLATION - TRADUCTION] \n \n" + EN + EN + "[TRANSLATION - TRADUCTION] \n" + FR + FR),
    modern(9), modern(10), modern(11),                        # Arabic, right to left
    modern(12, "[ ARABIC TEXT - TEXTE ARABE ] \n"),
    modern(13, "[ CHINESE TEXT - TEXTE CHINOIS ] \n"), modern(14),
    modern(15, " \n[ ENGLISH TEXT - TEXTE ANGLAIS ] \n"), modern(16), modern(17),
    modern(18, " \n[ FRENCH TEXT - TEXTE FRANCAIS ] \n"), modern(19),
    modern(20, " \n[ SPANISH TEXT - TEXTE ESPAGNOL ] \n"), modern(21),
    modern(22, " \nLIST OF SIGNATORIES/LISTE DES SIGNATAIRES \nAlgeria/Algerie -- 30/03/2007 \n"),
    modern(23, "Colombia/Colombie -- 30/03/2007 \nCosta Rica -- 30/03/2007 \n"),
]
labels = untc.label_pages(CRPD)
check("labels", kinds(labels), [
    "registration note", "parties as at registration", "parties as at registration",
    "reservations and declarations", "reservations and declarations",
    "reservations and declarations",
    "Arabic text", "Arabic text", "Arabic text", "Arabic text",
    "Chinese text", "Chinese text", "English text", "English text", "English text",
    "French text", "French text", "Spanish text", "Spanish text", "signatures", "signatures"])
check("authentic languages", untc.authentic_languages(CRPD[0]),
      {"arabic", "chinese", "english", "french", "russian", "spanish"})
check("English: registration note + English text",
      untc.select_pages(labels, "en", untc.authentic_languages(CRPD[0])), [0, 12, 13, 14])
check("French", untc.select_pages(labels, "fr"), [0, 15, 16])
check("Arabic (right to left)", untc.select_pages(labels, "arabic"), [0, 6, 7, 8, 9])
check("Spanish", untc.select_pages(labels, "spanish"), [0, 17, 18])
check("a language not in the registration", untc.select_pages(labels, "german"), None)
check("--lang codes", [untc.text_lang(x) for x in ("en", "FR", "ar", "zh", "ru", "es", "Norwegian")],
      ["en", "fr", "arabic", "chinese", "russian", "spanish", "norwegian"])
check("file names", [untc.lang_slug(x) for x in ("en", "arabic", "serbo croatian")],
      ["en", "ar", "serbo-croatian"])
try:
    untc.text_lang("other")
    check("--lang other is refused", "accepted", "SystemExit")
except SystemExit:
    check("--lang other is refused", "SystemExit", "SystemExit")
parts = untc.registration_parts(CRPD, labels, [0, 12, 13, 14], 11)
check("English part: PDF and printed pages",
      [(p["pdf_pages"], p["printed_pages"]) for p in parts if p["part"] == "English text"],
      [([24, 26], [15, 17])])
check("printed page from the newer running head", untc.printed_page_of(modern(70)), 70)
check("... with vol. 3200's non-breaking hyphen",
      untc.printed_page_of("Volume 3200, I" + chr(0x2011) + "54654 \n 171\n"), 171)
check("... in Annex A", untc.printed_page_of("Volume 2600, A-1320 \n 12\n"), 12)

# --------------------------------------------------------------------------
# The ICCPR's per-treaty English file, vol. 999, No. 14668: the Covenant and
# its Optional Protocol under one number, each followed by facsimile
# signature pages and by reservations in two columns (English and French
# side by side, the original quoted under a marker mid-page).
# --------------------------------------------------------------------------
print("ICCPR per-treaty English file (vol. 999)")
ICCPR = [
    "No. 14668\nMULTILATERAL\nInternational Covenant on Civil and Political Rights.\n"
    "Authentic texts: English, French, Chinese, Russian and Spanish.\n"
    "Registered ex officio on 23 March 1976.\nVol. 999,1-14668",
    old(172, "INTERNATIONAL COVENANT ON CIVIL AND POLITICAL RIGHTS\nPREAMBLE\n" + EN + EN),
    old(173, "Article 2\n1. " + EN + EN),
    old(256, "FOR AFGHANISTAN: \nPOUR L'AFGHANISTAN:\nPOR EL AFGANISTAN:\nFOR ALBANIA: \n"
             "POUR L'ALBANIE:\n"),
    old(257, "FOR AUSTRIA: \nPOUR L'AUTRICHE:\n"),
    old(282, "DECLARATIONS AND RESERVA \nTIONS MADE UPON SIGNATURE\n"
             "DÉCLARATIONS ET RÉSERVES \n" + EN + FR),
    old(283, "CZECHOSLOVAKIA TCHECOSLOVAQUIE\n[CZECH TEXT - TEXTE TCHEQUE]\nxx yy\n"
             "[TRANSLATION - TRADUCTION] [TRADUCTION - TRANSLATION]\n" + EN + FR),
    old(302, "OPTIONAL PROTOCOL TO THE INTERNATIONAL COVENANT\nON CIVIL AND POLITICAL RIGHTS\n"
             "Article 1\n" + EN + EN),
    old(303, "Article 6\n" + EN + EN),
    old(321, "FOR AFGHANISTAN: \nPOUR L'AFGHANISTAN:\n"),
    old(346, "DECLARATIONS AND RESERVA \nTIONS MADE UPON RATIFICA \nTION OR ACCESSION\n"
             "DENMARK\n" + EN + FR),
]
labels = untc.label_pages(ICCPR)
check("labels", kinds(labels), [
    "registration note", "English text", "English text", "signatures", "signatures",
    "reservations and declarations", "reservations and declarations",
    "English text", "English text", "signatures", "reservations and declarations"])
check("English: Covenant and Optional Protocol, no signatures or reservations",
      untc.select_pages(labels, "en", untc.authentic_languages(ICCPR[0])), [0, 1, 2, 7, 8])

# The "Other" file opens straight into the Chinese text: no registration note.
print("ICCPR per-treaty Other file")
OTHER = [old(202, "[CHINESE TEXT - TEXTE CHINOIS]\n"), old(203), old(225, "[RUSSIAN TEXT - TEXTE RUSSE]\n")]
check("labels", kinds(untc.label_pages(OTHER)), ["Chinese text", "Chinese text", "Russian text"])

# --------------------------------------------------------------------------
# Vol. 400, No. 5749 (1961): the authentic English and the Secretariat's
# French translation on facing pages, one marker at the start. No "Authentic
# texts" line in the registration note of that period.
# --------------------------------------------------------------------------
print("facing pages (vol. 400)")
FACING = [
    "No. 5749\nINTERNATIONAL BANK FOR\nRECONSTRUCTION AND DEVELOPMENT\nand\nBURMA\n"
    "Guarantee Agreement. Signed at Washington, on 6 June 1961\nOfficial text: English.\n"
    "Registered by the International Bank for Reconstruction and Development on 1 Sept 1961.",
    old(4, "No. 5749. GUARANTEE AGREEMENT\n" + EN + EN),
    old(5, "[TRADUCTION - TRANSLATION]\nNo 5749. CONTRAT DE GARANTIE\n" + FR + FR),
    old(6, "Article II\n" + EN + EN),
    old(7, "Article II\n" + FR + FR),
]
labels = untc.label_pages(FACING)
check("labels", kinds(labels), ["registration note", "English text", "French translation (Secretariat)",
                                "English text", "French translation (Secretariat)"])
check("English", untc.select_pages(labels, "en"), [0, 1, 3])

# Vol. 232, No. 3233, per-treaty English file: "Official texts" in the note,
# and the dash lost from the marker in extraction.
print("Secretariat translation in an English file (vol. 232)")
OFFICIAL = [
    "No. 3233\nNETHERLANDS\nand\nECUADOR\nAir Transport Agreement (with annex). Signed at Quito,\n"
    "on 14 December 1954\nOfficial texts: Dutch and Spanish.\n"
    "Registered by the International Civil Aviation Organization on 11 April 1956.",
    old(130, "[TRANSLATION   TRADUCTION]\nNo. 3233. AIR TRANSPORT AGREEMENT\n" + EN + EN),
    old(131, "Article 3\n" + EN + EN),
]
check("authentic languages", untc.authentic_languages(OFFICIAL[0]), {"dutch", "spanish"})
check("labels", kinds(untc.label_pages(OFFICIAL)), [
    "registration note", "English translation (Secretariat)", "English translation (Secretariat)"])

# The UN's own file of the TPNW (No. 56487, vol. 3370 not yet out): a bare
# "I-56487" head, and the Cook Islands' declaration quoted under its own
# [ENGLISH TEXT] marker, its heading only in the scan.
print("TPNW, file of an unpublished volume")
TPNW = [
    "I-56487\n1\nNo. 56487*\n____\nMultilateral\nTreaty on the Prohibition of Nuclear Weapons. "
    "New York, 7 July 2017\nEntry into force: 22 January 2021\n"
    "Authentic texts: Arabic, Chinese, English, French, Russian and Spanish\n",
    "I-56487\n2\nParticipant Ratification, Accession (a), Acceptance (A) \nand Approval (AA)\n"
    "Antigua and Barbuda  25 Nov  2019\n",
    "I-56487\n3",
    "I-56487\n4\n[ ENGLISH TEXT – TEXTE ANGLAIS ]\n",
    "I-56487\n5\n[TRANSLATION – TRADUCTION]\nDeclaration made upon Ratification "
    "Déclaration faite lors de la Ratification\nCUBA CUBA\n",
    "I-56487\n6\n[ ARABIC TEXT – TEXTE ARABE ]\n",
    "I-56487\n7\n[ ENGLISH TEXT – TEXTE ANGLAIS ]\n",
    "I-56487\n8",
    "I-56487\n9\n[ FRENCH TEXT – TEXTE FRANÇAIS ]\n",
]
labels = untc.label_pages(TPNW)
check("labels", kinds(labels), [
    "registration note", "parties as at registration", "parties as at registration",
    "reservations and declarations", "reservations and declarations",
    "Arabic text", "English text", "English text", "French text"])
check("English", untc.select_pages(labels, "en"), [0, 6, 7])
check("folio of the bare head", untc.printed_page_of(TPNW[7]), 8)
check("folio after blank lines (vol. 3200 Part file)",
      untc.printed_page_of("Volume 3200, I" + chr(0x2011) + "54654 \n \n171 \n \nNo. 54654"), 171)

# The record's authentic languages win over the note's.
print("authentic languages from the record")
check("label_pages takes them", kinds(untc.label_pages(FACING, {"english"})),
      ["registration note", "English text", "French translation (Secretariat)",
       "English text", "French translation (Secretariat)"])

# --------------------------------------------------------------------------
# Vols. 3100-3200: "[ TEXT IN ... ]" markers. A treaty authentic in neither
# English nor French keeps the authentic texts and the Secretariat's English
# translation, and drops its French translation.
# --------------------------------------------------------------------------
print("no English authentic text (newer markers)")
NOEN = [
    "Volume 3200, I-54000 \n 1\nNo. 54000 \nGermany \nand \nPoland \nAgreement. Berlin, 1 June 2015 \n"
    "Entry into force:  1 July 2016 \nAuthentic texts:  German and Polish \n"
    "Registration with the Secretariat of the United Nations:  Germany, 2 August 2016 \n",
    "Volume 3200, I-54000 \n 2\n[ TEXT IN GERMAN – TEXTE EN ALLEMAND ] \n",
    "Volume 3200, I-54000 \n 3\n",
    "Volume 3200, I-54000 \n 4\n[ TEXT IN POLISH – TEXTE EN POLONAIS ] \n",
    "Volume 3200, I-54000 \n 5\n[ TRANSLATION IN ENGLISH – TRADUCTION EN ANGLAIS ] \n" + EN + EN,
    "Volume 3200, I-54000 \n 6\n[ TRANSLATION IN FRENCH – TRADUCTION EN FRANÇAIS ] \n" + FR + FR,
    "Volume 3200, I-54000 \n 7\nArticle 5\n" + FR + FR,
]
labels = untc.label_pages(NOEN)
check("labels", kinds(labels), [
    "registration note", "German text", "German text", "Polish text",
    "English translation (Secretariat)", "French translation (Secretariat)",
    "French translation (Secretariat)"])
check("English: originals + English translation",
      untc.select_pages(labels, "en", untc.authentic_languages(NOEN[0])), [0, 1, 2, 3, 4])

# --------------------------------------------------------------------------
# Registered but not printed (article 12(2) of the GA regulations).
# --------------------------------------------------------------------------
print("not printed")
check("vol. 3000 wording", bool(untc._NOT_PUBLISHED_RE.search(
    "Not published in print, in accordance with article 12(2) of the General Assembly")), True)
check("vol. 2200 wording", bool(untc._NOT_PUBLISHED_RE.search(
    "Not published herein in accordance with article 12(2) of the General A")), True)
check("vol. 1400 wording", bool(untc._NOT_PUBLISHED_RE.search(
    "LOAN AGREEMENT'\nPublication effected in accordance with\narticle 12(2)")), True)

print()
if failures:
    print("%d failure(s): %s" % (len(failures), ", ".join(failures)))
    sys.exit(1)
print("all ok")
