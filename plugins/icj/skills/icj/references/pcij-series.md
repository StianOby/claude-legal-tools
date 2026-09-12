# PCIJ collection — what's in each series

The Permanent Court of International Justice published its work in seven
numbered series. Only A, B and A/B contain decisions and are exposed by
this skill.

## Series A — Collection of Judgments (1923–1930)

24 cases, codes A01–A24. Includes the foundational PCIJ contentious
cases:

- **A01 S.S. "Wimbledon"** (1923) — first PCIJ judgment.
- **A02 / A05 / A11 Mavrommatis Concessions** — diplomatic protection.
- **A09 / A13 / A17 Factory at Chorzów** — reparation, "Chorzów
  principle".
- **A10 "Lotus"** (1927) — jurisdiction over criminal acts at sea, the
  "Lotus principle" of permissive international law.
- **A20 / A21 Serbian Loans / Brazilian Loans** — international law of
  contracts.

Each case page lists the judgment, dissenting / individual opinions, and
any orders or annexes. Each link is a French-language descriptor pointing
to a PDF (typically French only for the early period; some have English
translations elsewhere).

## Series B — Collection of Advisory Opinions (1923–1930)

Advisory opinions of the same period. ~17 opinions. Notable:

- **B01 / B02 Designation of Workers' Delegate at the ILO** — early law
  of international organisations.
- **B04 Nationality Decrees Issued in Tunis and Morocco** — domestic
  jurisdiction reservation.
- **B05 Status of Eastern Carelia** — discretion to decline an opinion.
- **B14 Jurisdiction of European Commission of the Danube** — treaty
  interpretation.
- **B17 Greco-Bulgarian "Communities"** — minority protection.

## Series A/B — Collection of Judgments, Orders and Advisory Opinions (from 1931)

After 1931 the PCIJ merged its publication scheme. Codes look like
A/B 40, A/B 53, etc. Notable:

- **A/B 41 Customs Régime between Germany and Austria** (Anschluss
  opinion).
- **A/B 46 Free Zones of Upper Savoy and the District of Gex** (final
  phase) — treaty interpretation, *clausula rebus sic stantibus*.
- **A/B 53 Legal Status of Eastern Greenland** (Norway/Denmark) — title
  to territory, the *Ihlen declaration*.
- **A/B 70 Société Commerciale de Belgique** (Greek loans).
- **A/B 76 Panevezys-Saldutiskis Railway** — diplomatic protection,
  exhaustion of local remedies.
- **A/B 77 Electricity Company of Sofia and Bulgaria** — interim
  measures, treaty interpretation.

## Series C — Pleadings, Oral Arguments, Documents (out of scope here)

Not exposed by this skill. A separate hearing-documents skill is planned
to handle PCIJ Series C alongside ICJ pleadings/CRs.

## Series D, E, F (out of scope)

- **D**: Acts and Documents concerning the Organization of the Court —
  internal regulation, drafting history of the Rules.
- **E**: Annual Reports.
- **F**: General Indexes (consolidated).

These are listed at `https://www.icj-cij.org/pcij` for completeness but
not surfaced by the CLI.

## Code parsing

`pcij show` accepts:

- `A10`, `A 10`, `A-10` → series A, case 10.
- `B04`, `B 4`, `B-4` → series B, case 4.
- `A/B 53`, `A/B53`, `AB 53` → series A/B, case 53.

Codes are case-insensitive.
