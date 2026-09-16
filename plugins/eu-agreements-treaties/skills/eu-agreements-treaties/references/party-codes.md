# Party codes in the Consilium Treaties Office database

The search form's `Parties` values are **not ISO 3166**. Most states use
ISO codes, which is exactly what makes the exceptions dangerous: a wrong code
returns zero hits with no error. Always resolve a code with `__cs.parties()`
before trusting a count; the helper does this automatically inside
`search()`.

The form is an alphabetical index with one checkbox per *name form* —
"Norway - Kingdom of Norway" and "Kingdom of Norway (Norway)" both carry
`value="NO"`; 100 parties have a single form ("Greenland -"). 412 checkboxes
dedupe to **256 codes** (16 September 2026). The helper dedupes on the value
and keeps the short form as `name` — the form the ratification tables print.

## Member states with old EC codes (the trap)

| State | Consilium | ISO 3166 (wrong here) |
|---|---|---|
| Austria | `A` | AT |
| Belgium | `B` | BE |
| Germany | `D` | DE |
| France | `F` | FR |
| Italy | `I` | IT |
| Ireland | `IRL` | IE |
| Hungary | `H` | HU |
| Portugal | `P` | PT |
| Sweden | `S` | SE |
| Finland | `SF` | FI |

The other member states use ISO codes (`DK`, `NL`, `ES`, `PL`, `CZ`, `HR`,
`LU`, `GR` (not `EL`), `MT`, `CY`, `SK`, `SI`, `EE`, `LV`, `LT`, `BG`, `RO`).

## EU entities

| Code | Party |
|---|---|
| `UE` | European Union |
| `CE` | European Community — its *short name* on the site is "EC", but the *code* `EC` is **Ecuador** |
| `CEE` | European Economic Community (EEC) |
| `CEA` | European Atomic Energy Community (Euratom) |
| `CEC` | European Coal and Steel Community (ECSC) |
| `EEE` | European Economic Area (EEA) |
| `EM` | Member States of the EU (collectively) |
| `COM` | European Commission |
| `CUE` | Council of the European Union |
| `PAR` | European Parliament |

For "agreements between the EU and X" you usually want `UE` **and** `CE`
(and often `CEE` for anything before 1993) — the entity changed name with the
treaties. `search({parties: ["UE", "CE", "CEE"]})` is their union (site OR);
combine with `all: ["NO"]` for the counterparty.

## Collisions and near-collisions

| You type | Site meaning | You probably meant |
|---|---|---|
| `EC` | Ecuador | `CE` European Community — the helper stops with `ambiguous_code` |
| `EU`, `EEC`, `EEA` | not codes on the site | `UE`, `CEE`, `EEE` (suggested) |
| `AT`, `DE`, `FR`, `IT`, `IE`, `HU`, `PT`, `SE`, `FI`, `BE` | not codes | `A`, `D`, `F`, `I`, `IRL`, `H`, `P`, `S`, `SF`, `B` (suggested) |
| `CS` / `CZ` | Czechoslovakia / Czechia | both, for anything spanning 1993 |
| `CG` / `CGP` | Congo / People's Republic of the Congo | — |
| `KV` / `KVO` | two Kosovo entries (with and without the UNSCR 1244 footnote) | search both |
| `SZ` / `SWZ` | Swaziland / Eswatini | both |
| `MK` / `AYM` | North Macedonia / former Yugoslav Republic of Macedonia | both |

## Historical and renamed parties

| Code | Party |
|---|---|
| `CS` | Czechoslovakia |
| `SU` | Soviet Union |
| `YU` | Yugoslavia |
| `RDA` | German Democratic Republic |
| `ZR` | Zaire |
| `HV` | Upper Volta |
| `DA` | Dahomey |
| `SEM` | Serbia and Montenegro |
| `AYM` | Former Yugoslav Republic of Macedonia (alongside `MK` North Macedonia) |
| `SZ` | Swaziland (alongside `SWZ` Eswatini) |

A state can therefore appear under two codes; search both when the question
spans the rename.

## Third states commonly asked about from a Norwegian angle

Verified against the site's list on 16 September 2026: `NO` Norway, `IS`
Iceland, `LI` Liechtenstein, `CH` Switzerland, `GB` United Kingdom (not
`UK`), `US` United States, `RU` Russia, `CA` Canada, `TR` Türkiye, `GR`
Greece. All ISO except where the table above says otherwise.

## Full list

`data/parties.json` — 256 entries, `{code, name, long_name, names}`,
parsed from the captured search form (`NOTES.md` §4). `long_name` is `null`
for 13 codes whose long form is blank on the site: `AC` Andean Pact, `ASE`
ASEAN, `CS` Czechoslovakia, `DA` Dahomey, `GL` Greenland, `HK` Hong Kong,
`HV` Upper-Volta, `MAL` Malgache, `MS` Mercosur, `PAC` Central Africa Party,
`SU` USSR, `UN` United Nations, `UNR` UNRWA.
