# Automatic 2026 results intake

The **Update election results** GitHub Actions workflow refreshes registered
sources hourly, at minute 23, through January 31, 2027 UTC. It can also be run
manually from Actions, including outside that election window:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation --ref main
```

The tool publishes data to the separate `results-data` branch. It does not
rebuild the website, overwrite its reviewed participation catalog, or refit
switching/nonparticipation models.

## Get the complete results

Read `latest.json` on `results-data`. Its `results_commit`, `base_url` and `files`
inventory identify immutable result bodies, their byte lengths and SHA-256
checksums. Download `complete-results.zip` using that inventory. Branch history
retains previous snapshots; 30-day Actions artifacts are an additional convenience,
not the only copy.

The download contains all 14 complete numerical queries, selected source facts,
all 51 accepted jurisdiction shards and their complete baseline, source
qualifications, processing code, tests and checksums. It excludes respondent/voter
records, private fine cells, and publisher HTML/application templates.

| Query | Meaning |
|---|---|
| `snapshot.json.gz` | All current source channels and jurisdiction decisions. |
| `coverage.csv` | All 50 states plus D.C.; available, retained and missing sources. |
| `participation-observations.csv.gz` | Complete accepted observations plus separate refreshed source frames. |
| `house-candidates.csv` | Literal candidate counts, district, source clock and freshness status. |
| `house-state-results.csv` | Party sums only when every declared district snapshot is available. |
| `source-status.csv` | Each collected/retained feed, failure status and source URL. |
| `declared-products.json` | Official-directory discoveries awaiting scope/parser review. |
| `granular-source-queries.json.gz` | Complete registered county/reporting-unit statistical queries and source dispositions. |
| `declared-numerical-queries.json.gz` | Complete permitted tabular facts from newly declared products, with unqualified measures held. |
| `canonical-local-changes.csv` | Every qualified same-identity count update; appearances are not unique people or geographies. |
| Four `accepted-*.json` queries | Complete accepted House candidates, controls, native scope and state qualification flags. |

After extracting the ZIP into a fresh directory, run its literal command:

```sh
python3 code/reproduce.py replay --package . --output reproduced
```

Python 3.9+ and the project's existing `requests` dependency are required. Replay
verifies every pinned member and reproduces all query bytes without acquiring
sources or rerunning private survey fits. Optional packaged tests use `pytest`:

```sh
cd code
python3 -m pytest -q tests/test_results_intake.py tests/test_results_granular.py tests/test_results_native.py tests/test_results_native_workbooks.py tests/test_nationwide.py tests/test_current.py
```

## Verified statistical HTML delivery

Shared statistical HTML intake is verified through producer `a5f9ab2b`,
actual collector 43653231307, website workflow `e254d8f4` and
runtime `508a79e0` (job 43653666760).
The run refreshed 10,710 record appearances across
14 states, not unique people or disjoint geographies.

Clark County retains both accepted appearances of its native turnout parent;
Jefferson County supplies one parent and all 32 literal ward groups, including
the true zero/zero row; Monongalia County retains its separate complete/partial
reporting counters. The Wisconsin 32/32 counter is not all-machine completeness,
and literal Official Results does not cancel the native unfinished-canvass
caveat. Missing/held analytical rates remain held. Registration revisions
refresh existing display mirrors and withhold incompatible rates.

All 40 selected statistical rows and 173 complete factual tables are retained.
The maintained 164-test and canonical 170-test
suites pass, plus 11 packaged behavior tests. Fresh anonymous source/runtime
downloads reproduce all 14/113 outputs offline with zero requests. Actual
desktop/mobile production passes all 306 reader frames, every Wisconsin ward,
all nine model controls and both NM/MN native maps; images were inspected.
All 51 decisions and prior durable access stops survive. No fits, weights,
boundaries or comparison masks changed; the workflow-only engine pin needs no
new static Pages build.

[Complete acceptance](../data/participation-access/20261114-statistical-html-automatic-intake-01/acceptance.json),
[all jurisdiction decisions](../data/participation-access/20261114-statistical-html-automatic-intake-01/observations.json) and
[both complete downloads](DATA.md#statistical-html-automatic-intake)
record the scope. Nationwide county/precinct completeness is still open;
the full audit THEN beautification remain pending genuine prerequisites.


## Verified webform-source delivery

Actual collector43650846819 at producer `f19ea9c9` reported
allthree reviewed NE/SD products; consumer43651334289 activated
runtime `3f7b9c5f` using the unchanged website engine. Source
14-output/runtime113-output fresh public offline replays and all306 live reader
frames pass. Every2,086 NE/SD unit selection is checked at desktop/mobile, with
two ambiguous SD rows retained. Missing clocks are not retrieval timestamps;
159 pre-existing county parents remain unchanged. No new rates, fits or joins.
[Complete outcomes and acceptance](../data/participation-access/20261114-native-webforms-automatic-intake-01/acceptance.json) and
[both full downloads](DATA.md#current-webforms-source-automatic-intake) govern
this increment. Older hosted examples below are historical, not nationwide
county/precinct-completeness claims.


## What updates automatically

Actual hosted acceptance at producer `ed0f48d` (collector43641019948) refreshed
8,585 source-record appearances: AL1,233/CA58/MI770/MN4,279/MT2/NM2,237/NV2/TX4.
These are not new people or disjoint precincts. The complete source packet's14
outputs and consumer43641766958's113 runtime outputs freshly replay offline.
Runtime `ad3a4827` is live through website `05974f91`; actual desktop/mobile
checks cover all306 reader frames, eight-state county selections, both NM/MN
native maps and allnine model controls. All178 durable stops and the preceding
rolling last-good seed survive. Colorado parser capability is retained-original
acceptance, not fresh retrieval of its stopped workbook URL.
[Complete hosted outcomes and production acceptance](../data/participation-access/20261114-cross-state-automatic-intake-01/acceptance.json)
and [full source/runtime downloads](DATA.md#expanded-cross-state-automatic-intake)
govern this increment; the scope below is not universal county/precinct coverage.

The registry covers every jurisdiction's supplied official-directory disposition.
Existing parsers refresh provider early/mail and supported demographic feeds,
the four registered statewide administrative feeds (AL, NC, ND, OR), and House
district returns explicitly declared by the national source.

Registered local adapters also parse North Carolina county statistics, Minnesota
county/reporting-unit statistics, accepted Alabama general-election workbook
columns, and Connecticut town statistics. Shared structured families additionally
refresh California county statistics, Indiana's native `VotersVoting` records and
New Mexico's complete county/reporting-unit turnout table. They require the
reviewed native identities, election, measure, source-clock and parent-accounting
checks; Indiana's contradictory source zeros and independent county overrides
remain separate.

The shared PDF family reads reviewed county statistical parents, never candidate
totals. It checks the literal county/election, total-column or explicit fraction,
component arithmetic and report edition. An existing qualified registration frame
requires the matching native registration statistic; no new rate is approved.
For image-only first pages, pinned local RapidOCR 1.4.4 and PyMuPDF use two bounded
resolutions, requiring agreeing counts/registers/clocks and selected-number
confidence of at least .98. This is a same-engine resolution check, **not**
independent OCR validation. Conflicting meaningful text is never replaced by OCR.
Uncertain scans remain held. Collection requires the `pdf` extra; numerical
packet replay neither downloads OCR models nor re-extracts excluded originals.

Registered Texas reconciliation parents require explicit preliminary C/F/I or
official E/H/M voter/rejected/counted roles in their native column order.
Image-only forms additionally require the physical voter/rejected/counted header
bands; an extra or displaced number is not silently selected as counted ballots.
Attestation dates are not count-update clocks, and unresolved form labels remain
held. Existing accepted stable observation IDs survive only when their full
source/election/geography/measure identity tuple is unchanged.

The shared workbook family supports the reviewed Colorado all-returned county
tables and Wayne County's separate main/supplement statistical-unit workbooks.
Colorado mail and in-person modes reconcile separately to all-returned controls;
returned/processed counts are not promoted to cast ballots. Wayne's two component
inventories, duplicate parent controls and distinct decoded Excel clocks stay
separate; the administrative combination is not a printed native county parent.
Native zeros remain zero, blanks stay unknown, formulas are not executed, and
contextual registration/fractions do not become qualified turnout denominators.
Portable workbook behavior tests run without private originals; additional
retained-original cases are optional and skip only through their source fixture.
Parser capability does not clear a stopped source or establish fresh acquisition.

The reviewed summary family additionally registers King County's repeated global
ballot/register header and Hawaii's four native election-administration turnout
blocks. Every report page must retain its election, administration and source
clock; repeated King parents must agree, and Hawaii's mail/in-person components
and printed fractions must reconcile within the complete statistical column.
Maui retains its existing Maui/Kalawao membership, never two allocated counts.
These adapters preserve source-native measures, accepted identities and held
rates. A report edition older than the last successful capture is retained as a
failure, not activated over newer counts. A ballot question mentioning a primary
election does not change the report's separately checked general-election scope.
Current native report-status literals and printed fractions are bound to the
complete current query before entering displayed fields. Older notes and
rendered quality text are explicitly retained earlier-report context, not
current report statistics. Repeat projection must not accumulate that label.
FINAL remains a literal report edition, never inferred certification.
Retained-original acceptance and portable tests establish parser capability;
new hosted outcomes remain separately verifiable in the complete coverage query.

The reviewed legacy webforms family registers Nebraska's distinct TURN/PREC
products and South Dakota's PREC product. It requires the complete native county
inventory and literal election, publisher, status, unit, Ballots Cast and
Registered Voters column roles. Native unit-header literals remain separate from
canonical geography types. Only a unique native county-ID/rendered-unit-label
pair can refresh an existing observation; HTML whitespace is not an alias.
Physical row positions never resolve duplicate labels. All physical rows remain
in the complete query, including ambiguous units, while those accepted rows stay
held. Native state parents, printed reporting-unit counts and unit sums remain
distinct; absent county parents are never synthesized.

The shared statistical HTML family reads Clark County's complete turnout-method
table, Jefferson County's separate printed ballot/register parents and complete
ward inventory, and Monongalia County's explicitly headed Statistics block.
Candidate totals are never participation substitutes. It checks the reviewed
election, publisher, full native measure, literal unit identities and count-update
clock, rejecting older editions. All native tables remain in complete factual
queries; publisher application HTML is excluded from downloads.

Distinct accepted Clark appearances keep their existing IDs and view memberships.
Jefferson ward counts and registrations must reconcile to both printed county
parents; its native zero/zero ward is retained. The county reporting counter is
read only from BALLOT TOTALS, not repeated contest counters. Neither 32/32 reporting
nor the literal Official Results heading overrides the source's one-machine and
unfinished-canvass qualifications. Monongalia's complete/partial counters remain
separate; reporting is not certification. Existing qualified registration fractions
survive only with an unchanged compatible native stock; revisions withhold them,
and existing displayed registration mirrors refresh coherently. No new rates or
geographic joins are approved. Portable tests and retained-original acceptance are
parser evidence, not proof of fresh hosted collection or production activation.

These updates retain the entire accepted legacy measure contract rather than
newly qualifying it as ballots or people. Missing report clocks remain unknown,
not retrieval times. Earlier accepted clocks are retained separately and remain
available for rollback rejection across repeat captures. County parents, existing
geographic qualifications and withheld rates survive; no new rate is approved.
Portable tests exercise all three products through source planning, collection
and projection, including malformed-source retention and byte-stable repeats.

Source planning examines all 51 accepted jurisdiction shards. The current
baseline supplies primary-product registrations in 29 states; that number
includes unadapted products retained as factual review items, not 29 complete
native county collectors. Supported XLS/XLSX, delimited, JSON, HTML-table and
nested-ZIP products retain complete permitted factual cells, including blanks,
zeros and formula caches without executing formulas. Unreviewed columns do not
become participation counts merely because extraction succeeds.
Unqualified factual products are not participation observations. The operational
snapshot indexes directory-product facts through the byte/hash-pinned
`declared-numerical-queries.json.gz`; that complete query and the full selected
inputs remain inside the download, without duplicating every workbook in the
live snapshot. The existing decompression limit remains unchanged.

Changed identities/layouts remain held; these adapters do not approve new
boundaries or guarantee complete precinct coverage.
Alabama's registered workbook URL is distinct from newly declared ZIP products:
discovery alone does not alias a new release to that accepted source.

House collection is independent of county geometry/reconciliation. A county-map
failure cannot abort otherwise usable district returns. Full House baseline
counts remain available when the live declaration or a district is unavailable;
those rows are explicitly retained, not newly checked returns. D.C. has no voting
House seat. Distinct district clocks and accepted official HI/WY source scopes
remain visible; raw provider updates do not replace reviewed model endpoints.

This is not a universal parser for every state portal, PDF or newly posted
spreadsheet. Newly declared products with unfamiliar layouts remain review items
until an election/measure-specific parser and tests are registered. No guessed
endpoint, inferred missing count, or unreviewed precinct join is promoted.
The complete coverage query separately reports registered products, successful
native updates, source failures and factual products awaiting measure review.
Record refreshes count appearances: county parents and their reporting units,
or separate representations of one county, must not be added as unique voters.

## Failure handling and interpretation

Each source is independent. A failed request or changed schema retains its last
valid data and original source clock. HTTP 401/403, security challenges and
product stops persist on `results-data`, even if the operational HTTP cache is
lost. HTTP 429 also stops its host. The next run does not retry those routes or
switch clients/aliases. Removing a stop requires a separately reviewed access
change; a newer calendar date alone does not clear it.

Publication stages the complete result bodies and durable operational state,
verifies their anonymous immutable downloads, then activates `latest.json`.
An interrupted/failed run cannot replace the last valid pointer with empty
results. Identical content/provenance/code leaves the data branch unchanged;
checking again does not itself become a new native count clock.

Candidate votes are not ballots. Early/mail activity, registration stocks and
all-method participation are separate, nonadditive channels. Complete reporting
is not certification. Aggregate counts do not identify individual switching or
staying home. Existing behavioral qualification holds remain unchanged.

## Local operation

```sh
python3 -m scripts.results_intake collect \
  --registry data/results-intake/registry.json --work-dir /tmp/election-intake
python3 -m scripts.results_intake publish --work-dir /tmp/election-intake
```

`collect --offline` may reuse permitted, checksum-verified cached source bodies;
it makes no election-source requests and still honors durable access stops.
The initial source state and accepted numerical baseline are pinned in
`data/results-intake/registry.json`. Add or change sources there only with the
corresponding native scope review and focused parser tests.

## Automatic website and estimate consumer

The separate `scripts.automatic_runtime` consumer is enabled in the website's
own GitHub workflow and uses its token, not a shared cross-repository secret.
It pins reviewed producer `4d73fd2`; the initial live reader `4b08650` passed
actual Pages and no-override desktop/mobile acceptance. Collection runs hourly
at minute23 UTC and consumption at minute31. The assistant continuation is not
required for these numerical updates. Source-only publication by itself would
not establish live delivery; [the complete acceptance record](../data/participation-access/20261114-automatic-runtime-01/acceptance.json)
records both hosted jobs, public replay and actual website propagation.

```sh
PYTHONPATH=/path/to/research-source python3 -m scripts.automatic_runtime \
  --repository /path/to/website --work-dir /tmp/participation-runtime
```

It reads the pinned `results-data` snapshot once, advances compatible counts,
existing native bindings and all affected nine House family/profile cases, and
retains unsupported comparisons. Compatible registered-frame revisions reuse
the accepted probabilities; unchanged sources do not trigger private fits.
After the first run, a verified rolling seed is mandatory. Source failure never
resets estimates to the bootstrap seed or applies older retained local facts
over the website's last-good counts.

Each runtime packet includes the complete source-results ZIP, before/after
counts and native bodies, safe aggregate priors, every model query, code, tests
and checksums. Its fresh extracted command is:

```sh
python3 code/reproduce.py --replay-package . --output reproduced
```

Publication requires successful zero-network, complete-output replay, a
server-immutable full archive verified both authenticated and anonymously,
staged-body verification, and one atomic `catalog.json` plus
`automatic/latest.json` activation on the website's `participation-data` branch.
Count/native descriptors and models share the same immutable staged commit.
Interrupted staging is resumable; concurrent branch changes are not overwritten.
Subsequent numerical activations do not start a Pages build.

These are delivery guarantees, not observed individual switching/nonparticipation,
new geographic qualifications or final/certified nationwide results. The actual
GitHub-job, public full-packet replay and no-override production gates passed for
this increment; future parser/reader changes must satisfy the same gates.
