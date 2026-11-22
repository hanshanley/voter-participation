# California House county components, 2024 to 2026

The certified November 2024 Statement of Vote reports 130 county-by-district
components. Each component's two ballot-listed candidates are kept separately,
including contests with two candidates of the same party. The two candidate
sums reconcile independently to each of the 52 certified district totals.

The audit checks 519,723 California blocks against the published AB 604
assignments and the Census 119th and 120th Congress assignment files. The
old plan's county-by-district membership exactly matches the canvass
inventory. Fifty-nine historical components have one destination in the
new plan, preserving 3,801,886 candidate votes as intact source totals.
The other 71 require finer data. No precinct counts are inferred from
population, registration, or county totals.

Six new districts receive only intact components. CA-36 and CA-43 already
qualify in the separate comparison release. CA-11, CA-12, CA-34, and CA-37
still have candidate-frame holds. The audit does not promote any swing or
derive a participation count.

## Reproduce the five tables offline

From the extracted package, with CPython 3.12 and openpyxl 3.1.5:

```sh
env -u PYTHONPATH python3.12 scripts/california_house_component_audit.py inputs reproduced
diff -r outputs reproduced
```

The package contains the certified workbook, enacted block assignments,
and pinned Census archives and review. It does not contain Statewide
Database precinct files or attempt to recover masked counts.

- Certified Statement of Vote: `https://www.sos.ca.gov/elections/prior-elections/statewide-election-results/general-election-nov-5-2024/statement-vote`
- AB 604 assignments: `https://sdmg.senate.ca.gov/committeehome/2025-congressional-districts`
- Census assignments: `https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html`
