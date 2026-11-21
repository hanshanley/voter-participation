# North Carolina election participation archives

The North Carolina State Board of Elections links election-specific group-level
`history_stats` and `voter_stats` ZIPs from its [history catalog][history] and
[registration catalog][registration]. The `NC-YYYY-general-participation-statistics`
feeds check the catalogs, require both exact election links, and parse the native
TSVs. The weekly archive path reuses successful checks within the same UTC week.
The same intake discovers the November 3, 2026 pair when NCSBE links both files.
It does not download the individual voter lists or use OCR.

The exports are separate from physical ballot counts and congressional returns:

| Complete CSV | Unit and measures |
|---|---|
| `participation-nc-general-county-history.csv.gz` | Each election statewide and in all 100 counties; voter-history credits and registration statistics, no division of the two totals. |
| `participation-nc-general-state-groups.csv.gz` | Each election statewide by one dimension at a time: age, race, ethnicity or sex. Native categories, including blank codes, are preserved. Missing categories are not filled with zero. |
| `participation-nc-general-native-precincts.csv.gz` | Union of the two native county/precinct rosters for each election; credits, registrations, VTD code inventories and hold reasons. No rates, polygon joins, or allocation of nongeographic records. |

The displayed group fraction is `100 × voter-history credits / registrations
in that source group`. It is available only when the exact credit count and
the rate at the printed precision both match the NCSBE [2022][age22] or
[2024][age24] statewide age, race, or ethnicity table. The race and ethnicity
labels follow the [official codebook][layout]; the CSV keeps the native codes.
No sex, county, or precinct rate is calculated. For example, the 2022 age
26–40 archive count is 629,299, whereas the published age table has 629,298;
the archive count is retained and its rate is withheld. The 2016 and 2018
registration archives do not print their
native update date; that field stays blank. None of these statistics
establishes eligibility-population turnout, certified ballots, or vote choice.
The 2008 and 2010 registration layouts have no VTD field. The 2012 and 2014
registration update labels truncate the year; the original label is exported,
not inferred. In the 2008–2014 registration files, right-padding is removed
from the join key only after checking that no distinct native codes collapse
within a county. The printed code stays in the precinct download.

Refresh just these sources from the research checkout:

```bash
NC_SOURCES=$(python3.12 -c 'from scripts.north_carolina_participation import FEEDS; print(",".join(FEEDS))')
python3.12 -m scripts.results_intake refresh-selected \
  --registry data/results-intake/registry.json --work-dir "$WORK" --sources "$NC_SOURCES"
```

In the complete analysis ZIP, run
`python3.12 code/reproduce.py --replay-package . --output reproduced`
using the packaged dependencies. The nested source ZIP lists the exact
aggregate originals by URL, length, SHA-256 and local filename. To re-extract
them, collect those pinned originals in a local directory and run
`python3.12 code/reproduce.py replay --package . --output reproduced-from-originals --bulk-report-dir "$ORIGINALS"`
from the extracted nested source ZIP. Neither replay command acquires sources.

[history]: https://www.ncsbe.gov/results-data/voter-history-data
[registration]: https://www.ncsbe.gov/results-data/voter-registration-data
[age22]: https://www.ncsbe.gov/results-data/voter-turnout/2022-general-election-turnout
[age24]: https://www.ncsbe.gov/results-data/voter-turnout/2024-general-election-turnout
[layout]: https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/layout_history_stats.txt
