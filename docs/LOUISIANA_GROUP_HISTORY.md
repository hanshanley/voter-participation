# Louisiana statewide and parish group participation

The archive uses the [statewide catalog](https://electionstatistics.sos.la.gov/default.aspx?Stats=Post_Election_Statistics&Type=Statewide),
its corresponding parish catalog, and the Secretary of State's election inventory.
The inventory must declare an official November federal general-election date with
post-election statistics. The selected-year catalogs must link exact statewide
and parish files for that date. Local and December runoff dates are not substituted.
The adapter reads the native BIFF, XLSX, and legacy text formats without OCR.

Each accepted event contains all 16 source groups for the state and 64 parishes.
Registration party is not vote choice. The numerator is people reported as voting,
not necessarily physical ballots. The denominator is the source's post-election
stock of active and inactive registrations. The printed ratios are checked at their
native precision, but not promoted as independently qualified turnout rates.
Totals, race, registration-party, and party-by-race rows overlap. Do not sum them
together or add the statewide row to the parishes. No precinct geometry or historical
precinct identity is inferred.

As checked on November 21, 2026, 9 events reconciled: 1998, 2008, 2010, 2012,
2014, 2018, 2020, 2022 and 2024. The 2000 and 2004 parish files contain inconsistent
registration components for `PAR 26`; the 2002 statewide registration race split
does not match its total. In 2006, `PAR 52` differs across source registration-party
voting categories. In 2016, `PAR 55` reports 44,296 people voting in the parish file
and 44,297 in the statewide file. These are held rather than corrected by inference.

The scheduled late-archive intake checks each event independently. An incompatible
revision or unavailable source retains that event's last verified frame, if any.
Upward and downward revisions are both allowed when the two complete sources
reconcile. Catalog-only changes that do not alter accepted facts leave the accepted
source edition intact. The status log identifies the failed stage; the export marks
the retained frame and check week. The official reports do not supply a count-update
clock. This historical export does not modify the strict 2026 observation catalog.

Run the normal archive scope:

```sh
python3.12 -m scripts.results_intake refresh-selected --late-archives \
  --registry data/results-intake/registry.json --work-dir "$WORK"
```

For just Louisiana, supply `--sources` instead of `--late-archives`, with
comma-separated IDs of the form `LA-2024-general-election-group-history`. The
analytical output is `release/participation-la-historical-post-election-groups.csv.gz`.
For independent collection and offline comparison, install `xlrd==2.0.2`, supply
the project's current `source-stops.json`, and run:

```sh
python3.12 -m scripts.louisiana_group_history "$ORIGINALS" --source-stops "$STOPS"
python3.12 -m scripts.louisiana_group_history "$ORIGINALS" --replay reproduced.csv
```

The scoped source packet also pins the selected election record, exact source
catalogs and both originals for every admitted event. Its `code/reproduce.py
replay --package . --output reproduced` command reproduces the checkpoint;
`--bulk-report-dir` additionally re-extracts the original reports listed in
`inputs/bulk-report-originals.json` when those exact files are provided.

## Separate native precinct counts

The 2006–2024 spreadsheet years support 39,428 native precinct count rows.
The 1998–2004 text reports supply 15,755 more: counts in all 64 parishes match
both controls in each year, independently of the group subtotal holds, for a
combined 55,183 rows across fourteen elections. Each spreadsheet parish's
precinct vectors reconcile to that parish workbook's parent. A separate
count-only check compares the parish parent with the statewide workbook.
In 2016, precincts for `PAR 55` retain their reported
counts but are tagged with the 44,296 versus 44,297 control difference.
The 2006 disagreement in party-by-race categories does not change the total
count. These records are not a physical-ballot count, a precinct rate,
or a cross-year geographic join. The source row, native identifier and
control provenance travel with each record.

The `LA-2024-general-election-native-precinct-counts` feed is independent of
the group feed and uses the same catalog acquisitions. Add `--precincts` to
the offline replay command to reproduce the count-only CSV.
