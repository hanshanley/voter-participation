# Virginia precinct reporting

These are ballot-count products, not candidate returns. Neither product allocates
central voting to home precincts, supplies a precinct turnout rate, or qualifies
an election-day boundary join.

| Election | Source and decision | Complete numerical output |
|---|---|---|
| November 8, 2022 | Discover all 133 linked official locality reports from the statewide turnout page. Match their edition and each locality's early, Election Day, by-mail and provisional control; post-election mail belongs to the by-mail subtotal. Keep 2,545 physical Election Day precinct rows and 532 central rows separate, totaling 3,021,956 ballots. | `release/virginia-2022-native-precinct-counts.csv.gz` |
| November 5, 2024 | Discover the Election Turnout CSV from the official results API catalog. Keep all 2,669 printed rows, including blanks and provisional reporting units. The CSV totals 4,537,976, versus 4,526,538 summed locality API ballots and 4,535,314 certified statewide Total Voting. The CSV disagrees with 121 locality API counts. Its 6,434,637 registrations agree with the certified statewide registration count, not the API's 6,482,067. These are comparison controls, not evidence that the measures can be combined. | `release/virginia-2024-native-precinct-turnout-audit.csv.gz`, `release/virginia-2024-native-precinct-turnout-controls.csv.gz` |

The separate 2022 absentee statistics export has 6,214 statewide and locality
rows by native age, gender and receipt method. It reconciles to 992,227 returned
absentee ballots and preserves 64,992 applications without a recorded receipt
as a separate measure. Do not sum state and locality rows together, add these
figures to turnout totals, or read them as accepted ballots or group turnout
rates. See `release/virginia-2022-absentee-receipts-by-age-and-gender.csv.gz`.

The scheduled collector checks these archive routes weekly and keeps last-good
data labeled when a read or validation fails. A targeted refresh forces a check
without revisiting unrelated sources:

```bash
python3.12 -m scripts.results_intake refresh-selected \
  --registry data/results-intake/registry.json --work-dir "$WORK" \
  --sources VA-2022-native-precinct-counts,VA-2024-native-precinct-turnout-audit,VA-2022-absentee-receipts-by-age-and-gender
```

In the complete analytical ZIP, `python3.12 code/reproduce.py --replay-package .
--output reproduced` rebuilds the exports from retained source queries. The
collector ZIP also lists each pinned original in `inputs/bulk-report-originals.json`;
use `python3.12 code/reproduce.py replay --package . --output reproduced-originals
--bulk-report-dir "$ORIGINALS"` with the named original bytes to verify extraction
in addition to reproducing the queries. The original-report command expects the
complete bulk inventory in that checkpoint, not only the Virginia files.
