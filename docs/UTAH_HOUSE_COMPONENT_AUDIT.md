# Utah House county components, 2024 to 2026

The November 5, 2024 county returns reconcile to Utah's official statewide
candidate totals for all four House contests. The audit preserves county
and statewide party labels separately and matches candidate native IDs and
names. It uses public county aggregates only; 22 of 29 county catalogs mark
their precinct counts as protected.

The Census block assignments identify 36 historical county-by-district
components. Each of the 31 intact components has one exact destination on
the 2026 map. Five components intersect multiple districts, and every new
district receives at least one of them. The intact-component file preserves
complete, unaltered candidate totals for those units. It is not a complete
new-district baseline. No split votes are assigned, and no new swing is
qualified.

## Reproduce the six tables offline

From the extracted archive with CPython 3.12:

```sh
env -u PYTHONPATH python3.12 scripts/utah_house_component_audit.py inputs reproduced
diff -r outputs reproduced
```

Inputs include the Utah Lieutenant Governor's official public historical
catalog, its 29 declared locality responses, capture receipts, and the
complete 119th and 120th Congress Census block-equivalency ZIPs with their
review and checksums. Candidate votes are not ballots or turnout.

- Utah historical results: `https://electionresults.utah.gov/results/public/Utah`
- Utah election information: `https://vote.utah.gov/2024-election-information/`
- Utah GIS boundary vintages: `https://gis.utah.gov/products/sgid/political/us-congressional-districts/`
- Census congressional district files: `https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html`
