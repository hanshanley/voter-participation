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

Published collector state uses a checksum-bound gzip/base64 JSON envelope so
complete retained facts do not exceed Git's per-file limit. Decoding is bounded
and verified before reuse; older uncompressed states remain readable. This is
lossless storage, not a smaller query set or a changed runtime size limit.

If collection succeeded but publication failed, recover the completed Actions
packet without requesting the sources again:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation --ref main \
  -f reuse_collection_run=COMPLETED_RUN_ID
```

Recovery requires a completed collector run with successful source collection.
It verifies every packet member, the original report and version, reproduces
every numerical query, and refuses to discard any current durable access stop.
It also refuses to roll back a newer published collection.
The original packet, queries, source clocks and failed-run evidence are retained.
The recovery run's status does not change the original failed run's conclusion.

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
python3 -m pytest -q tests/test_results_intake.py tests/test_results_granular.py tests/test_results_native.py tests/test_results_native_workbooks.py tests/test_results_pdf_tables.py tests/test_results_json_statistics.py tests/test_results_pdf_boston.py tests/test_results_pdf_periodic.py tests/test_results_pdf_affiliations.py tests/test_results_pdf_jefferson.py tests/test_nationwide.py tests/test_current.py
```

## County affiliation and repeated-unit statistical PDFs

The shared collector includes explicit adapters for Oklahoma's 78-page
Absentee In-person Totals by Affiliation report and Jefferson County, Kentucky's
4,773-page general-election precinct report. Source planning retains all 77
accepted Oklahoma county templates and all 646 accepted Jefferson reporting
units. These are parser capabilities; hosted/live delivery requires its own
acceptance record.

Oklahoma updates only the existing in-person-early observations. Its separate
printed state total is an accounting control, not a new statewide observation.
Absent affiliation cells remain unknown; a printed zero remains zero.
Affiliation is administrative accounting, not candidate choice. County codes
are native identifiers, not declared FIPS, and no new denominator is supplied.

Jefferson checks every repeated page's election, literal unit and report clock,
and reads statistics only from the first page of each contiguous unit group.
All 60 suffix labels and 19 native zero totals remain literal. The separate
county-summary observation is not reconstructed from unit sums, and native
Mail is not relabeled returned envelopes. Reporting 646 of 646 is not
certification. Neither adapter adds geometry, rates or behavioral model fits.
Changed inventories, ambiguous statistics or regressed clocks retain last-good
observations. Complete queries, code, tests and safe fixtures remain in the ZIP.

PDF extras and the hosted collector pin `pypdf==6.16.0`, the reviewed extraction
engine. An unbounded dependency installed 7.1.0 in collector 43669246178;
cache-only Linux diagnosis reproduced changed statistical-header extraction
from the identical Jefferson PDF, correctly withholding its update. Dependency
upgrades require native-layout requalification, not relaxed column guards.

## Indiana, Boston and New Jersey statistical adapters

The shared collector also recognizes Porter and Monroe statistical JSON,
Boston's statement and 15 registered New Jersey periodic reports. These
adapters refresh 396 existing record appearances, not distinct people or
nationwide county/precinct coverage. Hosted/live acceptance is separate from
retained-source parser capability.

Porter preserves its literal UTC source clock, including subsecond precision.
Monroe retains all 103 distinct native units and its publisher-defined parent;
missing update clocks stay missing and genuine zero counts stay zero.
Native registration stocks are not automatically analytical denominators.
Existing map projections match exact native unit identities and complete prior
vectors across the older map/table IDs; geometry and map-specific qualifications
remain unchanged. Statement source-defined/all-method labels retain their own
original modes rather than promoting one representation's scope to the other.

Boston retains all 44 statistical contexts and 5,775 context rows. The selected
Senate context's Ballots Cast / Times Cast measure stays separate from the
contradictory summary Voters Cast total and zero registration. Current summary
parents must reconcile with current native units, not an old hardcoded count.
Candidate totals never replace statistical participation fields.

New Jersey retains literal selected parent roles, all native cells and clocks,
and the provisional-excluded EV + ED + mail-tallied subtotal. Union's
congressional parent is not its differing municipal parent. Middlesex's differing
county and municipal mail totals remain distinct. Sussex requires agreeing
complete OCR vectors at two resolutions and selected numeric confidence of at
least 0.98; this same-engine comparison is not independent validation.

The complete download includes every adapter, layout profile, portable test and
disclosure-safe aggregate fixture. Native labels, identities, views, geometry
holds, raw contradictions and unknowns survive. Failed source/clock/layout checks
retain last-good observations; no new rates, certified completion or demographic
model allocation follows from a successful capture.

## Reviewed statistical PDF adapters

The shared PDF adapter recognizes five explicitly reviewed products: Vermont's
247 municipalities, Somerville's city parent and 32 precinct/subprecinct rows,
Dover's city parent and six wards, and Wood/Kanawha county parents in West Virginia.
These 289 existing record appearances are not disjoint populations or nationwide
coverage. Hosted delivery acceptance is recorded separately from parser capability.

Vermont retains all 283 legislative reporting parts, 14 county controls, separate
summary controls and its printed state parent. Exact column/header rectangles,
complete numeric-cell coverage and all count reconciliations are required.
Wrapped labels remain literal alongside whitespace-only identity comparisons.
The date-only report clock must agree across pages and cannot regress; it is not
an invented midnight timestamp. Revised registration stocks withhold previously
qualified fractions instead of approving a new denominator.

Somerville retains every printed ward and city control, split-unit identity and
above-registration contradiction. Dover retains both complete statistical tables,
including physical column binding for adjacent registration cells; registration
affiliation is not vote choice. Its native 2026 election header governs, not the
2025 filename. Neither city supplies a count-update clock or an approved analytic
denominator. West Virginia uses literal statistical ballot parents, not contest
totals, and checks every page's election, county, status, clock and page index.
Complete/partial reporting counters do not establish certification.

New layouts, changed inventories, missing counts, ambiguous columns, regressed
clocks or failed reconciliation retain the last verified observations. Existing
geographic joins, identities, views, unknowns and qualification holds survive.
The complete source download includes the shared PDF reader, grouping code,
reviewed layout data and tests. Full numerical replay uses selected facts and does
not claim extraction of excluded publisher PDFs.

## Verified statistical-family delivery

Indiana statistical JSON, Boston's statement and all 15 registered
New Jersey periodic reports are verified through producer `595cb89c`,
collector 43665245545, publication recovery 43666625907,
consumer `4662aee3` and runtime
`8e86de8e` (job 43667024340).
These 18 products refresh **396 existing appearances**. The full collector now
refreshes **11,395 appearances across 19 states**, not unique people, disjoint
populations or nationwide county/precinct completeness.

All 103 Monroe units remain, including the changed split counts 69 and zero.
Porter is 59,951; Middlesex is 248,685. Boston preserves 275 units and all
44 statistical contexts; its selected Times Cast measure is not its conflicting
summary Voters Cast total. New Jersey retains provisional-excluded subtotals,
literal parent roles and source discrepancies. Sussex's two-resolution OCR
agreement is a same-engine check, not independent validation. Unknown clocks,
raw registers and held analytical rates stay qualified.

The original collection completed, but its 127.9 MB state file exceeded the
Git blob limit. A checksum-bound lossless 13.1 MB representation fixes storage;
the original complete packet and all queries were recovered without collecting
again. The original failed run remains failed. Sussex's renderer metadata,
confidence scores and three derived OCR token centers differ across platforms;
all 348 decoded numerical positions, native text, clocks and physical column
bands match. Both complete rendered image pins and OCR model pins match;
the selected numeric confidence threshold remains 0.98.

Exact native source identities and full prior vectors refresh existing Indiana
and Boston map dependencies despite older map/table IDs. No geometry, original
measure mode or rate qualification is promoted. The maintained
243-test and canonical 249-test suites pass.
Complete source/runtime packets freshly reproduce 14/113 outputs offline with
zero requests; all 113 public runtime bodies match. Actual desktop/mobile checks
cover all 396 new appearances, all 306 reader frames, the IN/MA/NM/MN native maps
and all nine model controls. Reviewed screenshots are hash-bound. All 51 source
decisions and prior access stops survive. No private survey refit, new geographic
join or static Pages rebuild occurred.

[Complete acceptance](../data/participation-access/20261114-statistical-families-automatic-intake-01/acceptance.json),
[all jurisdiction decisions](../data/participation-access/20261114-statistical-families-automatic-intake-01/observations.json) and
[both complete downloads](DATA.md#statistical-family-automatic-intake)
retain the scope. Broader source, historical, model and boundary gaps remain
open; the full audit THEN beautification still follow their genuine prerequisites.


## Verified statistical PDF delivery

Reviewed statistical PDF intake is verified through producer `214ae009`,
actual collector 43659940796, website workflow `3a28d572` and
runtime `f548be7f` (job 43660460633).
The run refreshed **10,999 record appearances across 17 states**, not unique
people or disjoint geographies. Five newly connected products refresh
**289 appearances across four states**: Vermont 247 municipalities,
Somerville one city plus 32 source units, Dover one city plus six wards,
and the separate Wood and Kanawha county parents.

Native counts, registrations, labels, source pages, physical coordinates,
clocks and controls equal the independently reviewed retained originals.
Vermont's sole cross-environment query difference is extraction-local
block/line/span/character glyph ordinals; both complete query bodies remain.
Native part totals, parent controls and printed percentages are not added
together or promoted to new analytical rates. Missing city clocks remain
unknown; Dover's native 2026 header governs despite its 2025-named file.
Somerville's above-registration contradictions and all reporting holds remain.

The maintained 187-test and canonical 193-test suites pass, with 23 packaged
PDF behavior cases. Complete public source/runtime downloads freshly reproduce
14/113 outputs offline with zero requests; all 113 public runtime bodies match.
Actual desktop/mobile production checks every PDF appearance, all 306 reader
frames, every Wisconsin ward, all nine model controls and both NM/MN native
maps; actual images were inspected. All 51 decisions and 178 durable stops
survive. No survey fits, weights, boundaries or comparison masks changed.
This workflow-only consumer pin required no new static Pages build.

[Complete acceptance](../data/participation-access/20261114-statistical-pdf-automatic-intake-01/acceptance.json),
[all jurisdiction decisions](../data/participation-access/20261114-statistical-pdf-automatic-intake-01/observations.json) and
[both complete downloads](DATA.md#statistical-pdf-automatic-intake)
retain the scope. Nationwide county/precinct completeness is still open;
the full audit THEN beautification remain pending genuine prerequisites.


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
