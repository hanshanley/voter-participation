# Texas House vote geography, 2024 to 2026

This audit keeps candidate votes separate from participation and does not
reassign votes to new districts. PlanC2193 was the 2024 plan; PlanC2333 is
the 2026 comparison plan. Texas Legislative Council publishes two distinct
geographies: election precincts and voting tabulation districts (VTDs).
The historical bulk vote CSV uses VTD identifiers. County plus the literal
reporting identifier is the join key; do not strip suffixes.

## Reproduce the four complete tables offline

From the extracted package, with CPython 3.12, openpyxl 3.1.5 and xlrd
2.0.2 installed:

```sh
env -u PYTHONPATH python3.12 scripts/texas_house_precinct_audit.py inputs reproduced
diff -r outputs reproduced
```

The inputs are checksum-pinned in the script. The package includes the entire
2024 general-election returns CSV from the council's comprehensive archive,
not the other elections in that archive. The control file is the full
comparison query from release `house-boundary-candidate-c938e802df97`;
it is not a new official statewide canvass.

- **District audit:** all 38 districts, separate precinct and VTD splits,
  archived vote totals and historical comparison controls. A matching D/R/Other
  total is not an individual candidate crosswalk.
- **VTD key audit:** both plan assignments for all 9,712 VTDs. No population
  figures or fractional report fields are used to allocate votes.
- **Precinct key audit:** both precinct inventories and exact key matches.
  An unmatched VTD key here is not evidence that the vote row is missing.
- **Source votes:** all 19,085 native House rows, including minor candidates
  and write-ins, with join decisions in both geographic systems.

The council's VTD archive includes 33 House contests. Nineteen agree with the
comparison controls by party group. All 30 boundary-only Texas holds touch a
new-plan split VTD with positive recorded House votes. The reports describe
which districts intersect a unit, not which ballots belong in each fragment.
Exact county canvass records for those fragments, reconciled to the complete
historical candidate controls, are needed before promotion.

## Sources

Texas Legislative Council, Creative Commons Attribution, via the Texas
Capitol Data Portal:

- `https://data.capitol.texas.gov/dataset/planc2193`: Red110 VTD and Red380
  split precinct reports for the 2024 general election.
- `https://data.capitol.texas.gov/dataset/planc2333`: Red110 VTD, Red375
  precinct, and Red380 split precinct reports for the same election vintage.
- `https://data.capitol.texas.gov/dataset/precincts`: Precincts24G_Districts.
- `https://data.capitol.texas.gov/dataset/comprehensive-election-datasets-compressed-format`:
  2024 general VTD returns. The council notes that its redistricting data can
  differ from official state and county returns.
