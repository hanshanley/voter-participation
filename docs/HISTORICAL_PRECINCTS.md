# Historical precinct returns

The bulk collection covers 2016, 2018, 2020, 2022 and 2024, including midterms.
Read the [255 state/year decisions](../data/historical-precinct-coverage/20261112-03/queries/all-255-state-year-decisions.csv)
before combining files. Source presence, numerical queries, ballot fields and
existing presidential geometry are separate columns. None certifies complete
precinct coverage, demographic turnout or a longitudinal boundary match.

| Year | Jurisdictions with a selected source | Important qualifications |
|---|---:|---|
| 2016 | 51 | MEDSL federal queries; full five-office source partitions retained |
| 2018 | 51 | MD election-day and allocated variants separate; VA compiled party totals; ME towns/WI wards |
| 2020 | 51 | VA native-unit CSV includes administrative units; NJ supplement has only 13 county files |
| 2022 | 51 | Reused held MEDSL originals and selected House queries; DC delegate separate |
| 2024 | 51 | Reused held MEDSL federal queries and existing presidential layers |

These are **jurisdictions including DC, not counts of complete states**.
The existing NYT layers contribute presidential-only coverage to the ledger;
they are not House returns or ballots cast. Different files can overlap.

## Collected numerical data

- MEDSL 2016: 22 originals, including five nonduplicated office ZIPs.
  Complete federal query: 4,060,918 rows, retaining all 37 native fields.
- OpenElections: 85 statewide-named CSVs plus 414 supplemental files,
  totaling 13,003,540 rows. Supplemental county files are collected in one
  pinned-tree batch, not through individual county-site research.
- Official AL/KS/PA 2018/2020: 23 products and 1,161,107 cells/rows, plus
  every Kansas supplemental worksheet grid. Alabama supplies 4,351 native
  ballot-count cells; these are not an additive participant total.
- Official NC 2018: 183,723 rows from the declared historical ZIP, with
  all 16 columns including the trailing blank header and voting methods.
- Independent MGGG complements: MD2018 has two distinct 1,809-row tables
  (merged election-day-only, versus publisher-allocated early/absentee/
  provisional plus election-day counts); VA2018 has 2,439 compiled attribute
  records; VA2020 has 152,025 native candidate-unit records, preserving central
  absentee/provisional units, source clocks and multi-seat races.
  Original datasets, exact DBF octets, notices and ODbL/DBCL attribution remain.
- Existing MEDSL 2022/2024: all 51 jurisdiction source files per year are
  held. Their 12,310,863 / 18,383,653 native rows were not downloaded or
  reduced again merely to build this ledger.

Preserve literal counts, suppression, corrections, unknowns, source units,
candidate/party labels, stages and voting modes. Never add supplied totals
to their component modes. Native registration zeros are not qualified turnout
denominators; candidate votes are not ballots. PA county ordinals are not
FIPS, and its separate registration files have a different schema. Kansas
wide county supplements remain unmerged. Native ward/town/precinct flags
do not approve geometry or cross-year identity.

## Reproduce and update

The collectors use the shared content-addressed Store, access-stop ledger and
pinned originals. Keep successful versions immutable and use a new directory
for a changed selection. An unchanged collection verifies its original bytes
without requesting sources again; an unchanged numerical query verifies its
manifest without parsing the original again.

```bash
python -m scripts.openelections_history_batch \
  --repositories repositories.jsonl --output statewide
python -m scripts.openelections_history_rows \
  --source statewide --output statewide/derived
python -m scripts.openelections_history_batch \
  --repositories repositories.jsonl --supplemental-from statewide \
  --output supplements
python -m scripts.openelections_history_rows \
  --source supplements --output supplements/derived
python -m scripts.verify_openelections_history_rows \
  --source supplements --output supplemental-verification.json
```

`repositories.jsonl` is the recorded public OpenElections repository inventory.
The supplement command reuses already-held branch/tree metadata, selects only
missing statewide-file years and preserves native product scopes. Do not retry
denied products through another client, cache or mirror.

The recipe-driven tabular archive adapter also supports the official NC TSV:

```bash
python -m scripts.historical_tabular_archive_rows \
  --spec data/historical-tabular-source-specs/20261112-01/nc2018.json \
  --source-root ORIGINALS --output NEW_OUTPUT
python -m scripts.historical_precinct_coverage \
  --inputs data/historical-precinct-coverage/20261112-03/inputs.json \
  --output NEW_COVERAGE
```

CSV processing uses the standard library. The official XLS/XLSX adapters use
`xlrd==2.0.2` and `openpyxl==3.1.5`; DBF attributes use `pyshp==3.1.6`.
The same generic tabular adapter accepts the VA2020 plain CSV recipe;
`scripts.historical_gis_attributes` accepts the MD/VA2018 recipe, both under
`data/historical-tabular-source-specs/20261112-01/`.
Complete packets preserve the exact archived
processing code, which need not equal later acquisition-only fixes.
The general current-runtime update workflow remains a separate unfinished task.

## Verification and delivery

All 46 focused source/compiler/coverage/publication tests pass. Independently
checked every native field in the 2016 federal query, both OpenElections
collections and NC 2018. The MGGG complements' native DBF cells were independently checked
with a standard-library binary reader, not the primary PyShp engine; every
VA2020 CSV cell and canonical field was checked. The official-state packet reproduced all 19 outputs
including 15 Kansas grids offline, with its 36 archived tests.
The final 2016 packet differs from the fully replayed predecessor only in
atomic-cache code, its regression test and checksums; every numerical query
and processing module is byte-identical, and seven final archived tests pass.
That is not a claimed wholesale replay of the final packet.

All five final ZIPs and every nested packet/member checksum also pass. A fresh
archived-code run passes all46tests with network/DNS/child commands blocked
and reproduces all coverage, NC2018 and MD/VA2018/2020 outputs byte-for-byte.
The entire multiyear native collection was not reprocessed wholesale.

These checks establish source-field consistency and reproducibility, not
independent election-total truth or complete precinct turnout. New map joins
have not been approved, and no existing website model or map was replaced.
[Download the complete selected query set](https://github.com/hanshanley/margin_of_error/releases/download/participation-historical-precincts-20261112-01/complete-analysis.zip)
(874,127,644 bytes; SHA256
`cf7958ae88c713972c6bebb119daca864d7f789384ec832b662f8e227654c2a9`).
Immutable release443532631 has all eight full assets verified authenticated
before publication and anonymously afterward; [Downloads](DATA.md) also lists
the complete component packets and coverage CSV. Whole held2022/2024 native
archives and official-state workbook/document templates remain local pending
exact rights/version linkage; their complete selected numerical queries are
included. Re-extraction of the official-state templates needs those separately
retained originals, not just this public factual-query packet.
Original notices remain source-specific; no blanket MIT license is asserted
for every source or native document template.
