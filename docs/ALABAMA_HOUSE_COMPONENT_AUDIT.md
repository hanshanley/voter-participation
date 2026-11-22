# Alabama House reporting units and county components, 2024 to 2026

The Alabama Secretary of State's November 5, 2024 precinct archive contains
67 county workbooks. The 5,572 reported House candidate cells, including
true zeros and write-ins, reconcile to the historical comparison controls
in all seven old districts. Blank cells and overvotes and undervotes are
not candidate votes.

The two pinned Census assignments identify 73 old county-by-district
components. Seventy have an exact single destination, preserving 1,823,907
candidate votes without splitting or estimating any totals. Covington
in old District 1, Elmore in old District 6, and Jefferson in old District 7
are split. They contain 12,834 candidate votes in reporting units labeled
absentee or provisional; those votes are not assigned to a home precinct.
Reporting-unit names do not establish an election-effective precinct
crosswalk. The audit qualifies no new swing and measures no turnout.

## Reproduce the five tables offline

With CPython 3.12 and xlrd 2.0.2, from the extracted ZIP:

```sh
env -u PYTHONPATH python3.12 scripts/alabama_house_component_audit.py inputs reproduced
diff -r outputs reproduced
```

The package includes the original state archive, complete historical
comparison query, Census assignment archives, and their review. The
historical comparison query is a reconciliation control, not a separately
published official canvass.

- Alabama Secretary of State: `https://www.sos.alabama.gov/alabama-votes/voter/election-data`
- Census assignments: `https://www.census.gov/programs-surveys/decennial-census/about/rdo/congressional-districts.html`
