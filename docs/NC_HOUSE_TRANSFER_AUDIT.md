# North Carolina House vote geography, 2024 to 2026

The official July 23, 2024 precinct-to-block crosswalk matches all 18,826
blocks that moved into or out of NC-01 in the pinned 119th and 120th
Congress Census assignments. The moved blocks touch 186 precincts. Nine
precincts span the new NC-01 boundary and report 19,946 2024 House candidate
selections across five voting modes. Their votes are not allocated to the
new districts. Two unchanged blocks with unassigned precincts are exported
separately rather than filled in.

The NCSBE statewide results and precinct-sorted results are distinct
products. The latter is not a certified canvass. The reconciliation uses
literal district, county, candidate and party keys; it keeps zero and
missing entries separate, excludes overvotes and undervotes from candidate
totals, and retains the precinct-sort transfer method. The exports do not
count ballots or show turnout. No new swing is qualified by this audit.

## Reproduce the six tables offline

From the extracted package, with CPython 3.12 and pyshp 3.1.8:

```sh
env -u PYTHONPATH python3.12 scripts/nc_house_transfer_audit.py inputs reproduced
diff -r outputs reproduced
```

Inputs include the complete statewide and precinct-sorted returns, the
unchanged DBF member of the official precinct shapefile (geometry is not
used by this procedure), and the complete pinned national block assignments.

Original sources:

- `https://www.ncsbe.gov/results-data/election-results/historical-election-results-data`
- `https://s3.amazonaws.com/dl.ncsbe.gov/ShapeFiles/Precinct/SBE_PRECINCTS_CENSUSBLOCKS_20240723.zip`
- `https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html`
