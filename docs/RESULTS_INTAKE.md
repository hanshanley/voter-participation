# Automatic 2026 results intake

The **Update election results** GitHub Actions workflow refreshes registered
sources hourly, at minute 23, through January 31, 2027 UTC. It can also be run
manually from Actions, including outside that election window:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation --ref main
```

The tool publishes data through the `results-data` tag. The website runtime
likewise uses the `participation-data` tag; `main` is the only code branch.
Existing raw data URLs and immutable snapshot/download URLs remain unchanged.
Data tags advance with an exact-head lease and an ancestry check, so a stale
writer or rollback cannot discard published history. Do not recreate data,
feature, diagnostic or source-publication branches.

The tool does not
rebuild the website, overwrite its reviewed participation catalog, or refit
switching/nonparticipation models.

## Nationwide congressional returns

The same hourly collector also reads the two national NPR/AP bulk inventories
declared by the published 2026 House and Senate pages and their `app.js`.
`data/results-intake/congress.json` is the single reviewed provider declaration;
there is no manually maintained list of race endpoints. Advertised additions
are discovered on the next collection. Civic's stopped national feed and
documentation routes remain stopped; NPR is an independently published source.
Local participation-reader holds do not block these two bulk requests.

`results_congress.py` keeps provider IDs, Senate seat classes, regular/special
elections, general/runoff stages and RCV phases/rounds separate. Nonvoting
House jurisdictions are not counted as voting districts. Each candidate keeps
its literal party, native ID, zero or explicit unknown count, and aggregate
Other role. Missing candidate inventories, changed identity, older native
clocks and same-clock fact changes retain the last good race, not a false zero.
Genuine increases and decreases require a newer native count clock.

The additive `congress` snapshot follows the existing intake/runtime handoff.
The existing explorer provides current race/candidate tables, complete statewide
House comparisons, seat-qualified Senate comparisons, per-contest source dates,
freshness and every raw/held decision. Complete queries include both current
source facts and the delivered previous-election inputs. Full CSVs and the
complete reproducible source/runtime ZIPs accompany every version.

House statewide comparisons use the complete previous House inventory.
District-ID arithmetic remains visible but is held when cross-year boundary
stability is not qualified. Changed party coverage, unopposed races, multiple
nominees, missing counts, stages and RCV rounds retain their own qualifications.
The reviewed 2020 regular-seat-cycle Senate baseline binds Class II only;
special/unexpired or intervening-special seats cannot borrow it. Native clocks
are source epochs; the election date is explicitly the reviewed national-index
context, not an invented per-race field. Candidate votes are never turnout.

New returns do not automatically replace frozen behavioral-model inputs.
Those require a separately reviewed candidate/source/frame match. Existing
scientific seeds, fitted models, participation frames and immutable downloads
are preserved.

For a bounded national refresh using the latest complete accepted state:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation \
  --ref main -f congressional_only=true
```

This acquires both national feeds and retains all noncongressional inputs
without reacquiring them. Normal hourly collection still updates its registered
participation sources as well. The existing minute-31 website workflow publishes
data only, atomically, through `participation-data`; later returns require
neither an assistant nor a Pages build.

## Supported analytical release and selective recovery

The accepted finite release is source `30bb6e95` / runtime `9c7117fb`.
[Exact coverage and complete downloads](../data/participation-access/20261116-supported-analytical-release-01/coverage-and-downloads.json)
include 18 compressed CSV/query products in the same complete numerical
archive, with native dates, qualifications and explicit omitted-frame reasons.
There are now 132 complete runtime outputs, versus the previous 113.
This increases integrated/exported product coverage, not the number of people
observed or newly qualified comparisons.

The handoff is `results_intake` -> `automatic_native_refresh` ->
`automatic_estimates` -> `automatic_runtime` -> the existing explorer.
The reviewed release adds complete administrative/rate, historical survey,
2026 modeled demographic, recorded/qualified House comparison and conditional
mechanism CSVs to the same runtime archive. Each changed observation has a
source-to-analysis decision explaining which analytical prerequisite is absent.
Existing Senate/governor snapshots and complete queries remain a distinct frozen
product with their own source clocks and qualifications, not hourly refreshed races.
Local counts do not become statewide registered controls or choice histories.
No new fit or statewide-to-local allocation is performed.

The complete `source-to-analysis-effects.csv.gz` distinguishes a captured
source, changed count, available compatible fraction, changed fraction,
recorded electoral comparison and conditional model update. Reused observations
keep their own clocks and are not relabeled fresh. In this selected capture,
only Walworth is newly captured; all other collector entries and native clocks
are exactly preserved against the actual immutable preceding collector state.
Walworth's 46,612 county ballots do not supply a registration denominator,
statewide control, candidate-choice endpoint or joint history. Cape May retains
its compatible 42,442/76,899 native-registration fraction and exact
`11/12/2026 03:34PM` clock. Neither licenses a new model probability.

`reviewed-eligibility.json` version `20261116-supported-release-03` records
the actual 17 House and 51 registration reviews. None of their specific holds
resolved, so the existing 33 qualified comparisons, 34 scenarios and old
scientific seed remain for evidenced reasons. `source-product-dispositions.json`
accounts for every pinned source-semantics error: two repaired parser defects,
seven unsupported products, nine external evidence holds and one native
reconciliation conflict. It recovers attempted URLs from `source_plan()` when
source-status rows leave them blank. These are distinct from transport failures
and from the two subsequently repaired hosted integration defects.

Source run 43797815095 passes 657 tests, 11 optional skips and 17 subtests;
all 14 source outputs reproduce offline. Runtime run 43799309629 computed and
replayed all 132 outputs before its original Git stage-tag push failed with
exit 128. Its precise Git cause is unknown because stderr was not exposed.
Publication alone was recovered from the exact already-published immutable
archive, without recollection, recomputation or fitting. Actual hosted attempt
2 then succeeded as an unchanged no-op against that runtime and data commit.
Final full public-body, extracted offline replay and desktop/mobile acceptance
are recorded in the [release validation](../data/participation-access/20261116-supported-analytical-release-01/acceptance.json).
Preserve the original failed run and journal when diagnosing a post-computation
publication failure; do not restart accepted collection or replace immutable
analysis bodies merely to retry Git publication.

For a diagnosed source-only failure, `refresh-selected --sources SOURCE_ID`
starts from the latest validated complete collector state, acquires only those
registered products, and reuses all other observations, candidate facts and
native clocks. Unknown IDs, incomplete prior state and failed captures refuse
replacement publication. `collection_scope` records this reuse explicitly.
The normal hourly collection remains unchanged.

Cape May uses the reviewed PDF-parent dispatch and physical page 2, not the
administrative-subtotal parser. Its wrapped six-method header and native
`Registered Voters - Total` label bind the existing compatible fraction.
The native clock is `11/12/2026 03:34PM`, with no inferred timezone.

Walworth's original summary was incorrectly assigned its declared municipality
sibling URL. A source/observation/inventory-pinned bridge selects the originally
declared summary document 22455, preserving the registered source ID and
`Ballots Cast: 46,612` measure. Municipality Cards Cast/Voters Cast and candidate
Total Votes remain distinct and cannot substitute for that statistic or clock.
The corrected summary supplies no qualified registration denominator.

The pinned 19-error review distinguishes two implementation defects, seven
unsupported numerical products, nine source-evidence holds and Mohave's
four-ballot native reconciliation conflict. Williamson and unreadable handwritten
Texas evidence retain the existing confidence thresholds.

## Shared statistical headers and reviewed report pages

The shared county-PDF reader recognizes Jefferson's wrapped TOTAL-first header
with Election Day, Mail, Walk-in Excuse, Walk-in Early and Provisional columns.
All five components must be present in their reviewed order and reconcile with
the native total. The complete header and statistical row remain in the query.
The current literal result status is refreshed; a missing status stays unknown,
not the initial report's label or an independent certification.
Both text-layer and scanned county totals reject clocks older than their
query-bound last-good capture, not just the frozen initial observation.

Platte's reviewed selector is retained verbatim: `physical_page: 20` identifies
the reviewed printed page 20/26, physically PDF page 21 after an affidavit.
This explicit profile does not reinterpret page selectors for other sources.
It binds the native Turnout registration, Ballots Cast and percentage columns,
never the adjacent proposition-vote columns. All four displayed turnout rows
are retained, but their contest-filtered children are not a complete county
partition and are not summed to replace the printed county total.

Platte uses the reviewed upright OCR mode at two resolutions. A bounded crop
of its native Date/Time fields meets the same .98 clock confidence threshold;
it must agree with the full-page reading. The literal CST timezone is retained.
Missing absentee registration/percentage remains missing, not zero. Source
registration stocks and percentages remain context only: no new denominator,
analytical rate, completed-counting, geography or estimate qualification.

## Cole County: upright precinct-statistics grid

Cole's reviewed profile reads the native Ballots Cast column and Total row,
not candidate votes. It retains all 28 locality rows, the separate ABSENTEE
row, and the printed county parent. Absentee repeats the county registration
stock; that stock is not added a second time. Row percentages, locality stocks,
ballot components, physical columns and both OCR resolutions must reconcile.
The profile disables text-angle classification for this reviewed upright grid:
the generic classifier can rotate a printed 999 into 666. Other profiles keep
their existing OCR defaults. Missing or low-confidence counts fail closed,
not to zero; source clocks cannot regress behind the last-good report.

The native registered counts and percentages remain source context only.
This adapter does not qualify an analytical denominator, completed counting,
precinct geometry or new estimates.

## Greeley County: source-defined workbook turnout

The reviewed Greeley workbook profile reads the three literal statistical
header cells, not candidate totals. It checks the source's administrative and
counted-provisional equations and preserves every workbook cell in the complete
query packet. Unknown XLSX dimensions stay unknown instead of causing a BIFF
`nrows`/`ncols` schema failure.

The reported total remains `voters_reported`, not ballots cast or unique people.
Its existing same-report registered-voter fraction stays qualified only within
that source frame; it is not eligible-population turnout or a new estimate.
The native count clock remains missing. Server metadata is not substituted.
One county is covered; the other 104 county totals remain unknown.

The display uses a reviewed count-independent measure label. The initial
accepted numeric literal remains explicitly historical, while the current
equation, registration stock and printed fraction are refreshed from the new
source. This narrowly scoped display alias does not change observation IDs,
source units, denominator basis, geometry or other identity checks. Invalid
equations, unknown counts, formulas and changed source frames fail closed and
retain the last-good observation.

## Boone County: reviewed statistical PDF mapping

The shared county-PDF adapter recognizes the native **Ballots Cast - Total**
label when the accepted observation's native record, source fields and physical
selector explicitly agree on it. It does not guess aliases from candidate votes.
The statistical header's wrapped Election Day label and ordered Central columns
are checked against every ballot component and the printed total.

The current native registration stock, printed fraction, report status and
unknown-timezone report clock remain available in the complete numerical query.
These are source context, not newly qualified turnout denominators, certification,
map joins or cross-year estimates. A missing count is not converted to zero;
changed roles or inconsistent statistics hold the last-good observation.
Subsequent captures also reject clocks older than the last-good full query,
not merely older than the frozen initial observation. Source stops are enforced
before acquisition. Retained-original regression checks and actual hosted
collection are separate acceptance steps.

Last-good native updates are projected even when the next capture fails. Their
original source pin, clock and complete query remain attached; the failure is
still reported as `retained_after_failure`, not counted as a fresh capture.
This requires a preserved observation receipt and an exact pin of the accepted
identity, election, geography, measure, count, denominator, report clock and
source identity against which the update was parsed. Mutable presentation/query
metadata is not part of that frame pin. It preserves revised counts,
true zeroes and unknowns instead of reverting them to the frozen initial count,
without overwriting an independently advanced baseline with older retained facts.

## Broome County: automatic contest-scoped report intake

The default collector follows Broome's official results page and its declared
dashboard, client and election metadata to two native reports. Its complete
governor-context query retains **126 reporting units, 17 municipality controls
and one contest control: 144 rows**, with literal labels, counts, registration
stocks, printed percentages, source pins and protection notices. The complete
query is retained in the source packet; its factual fixture and behavioral
tests are also exported for portable execution.

These are **not qualified whole-election turnout totals**. The governor-context
control is 68,955, while a separately printed congressional control is 69,086.
The unexplained 131-count difference is not repaired or assigned a cause.
The actual 0/0 row remains distinct from missing data; Dickinson 3's native
611/122/500.82% is preserved without approving a turnout rate. Raw registration
stocks are not analytical denominators.

The municipality report supplies no count-update clock. The separate summary's
11/09/2026 16:53:10 has no timezone and belongs only to that summary.
API publication clocks are used for edition-rollback checks, not substituted
for either report's count clock. Changed or protected layouts fail closed;
stopped sources retain the entire last-good query and original observation metadata.

This adapter produces **zero canonical count updates** and withholds rate,
whole-election, unique-person, geography, cross-year and estimate-update
qualification. Retained-original/default-collector and portable package checks
are distinct from accepting an actual new hosted capture. No new website count,
map or estimate activation is claimed by this source-only integration.

## Verified SC delivery and DE/DC holds

South Carolina's native statewide **2,054,835** participation snapshot now
passes unattended hosted capture and data-only website delivery. Its complete
mode query, printed-percentage anomaly, unknown exact registration stock and
missing count clock remain explicit; publication/certification is not a count clock.

Delaware and D.C. adapters pass full retained-original and revised-input tests,
but their actual hosted routes are **source-stopped: zero fresh updates**.
Their last-good count shards and Delaware's visible statewide mirror remain exact;
D.C. and North Dakota's existing native map bodies also remain exact. Do not retry
or bypass stopped routes. A runtime repair now propagates future same-identity,
exact-prior-view statewide updates to the visible counter, including true zero.
Its controlled revised/zero tests are not new publisher observations.

Source `fc7581a7` / collector 43709515573,
engine `2e0e2507` / workflow `6cd0fdc4` and
runtime `7416e6a3` / job 43710775489 are verified.
The hourly GitHub pipeline, not assistant retrieval, updates qualified counts and
compatible estimates. This delivery starts **no Pages build** and makes no new
fit, demographic-turnout, geographic-allocation or map-approval claim.
Actual granular refresh remains **18,242 record appearances across 26 states**,
not people or complete local coverage; SC's state-only feed is separate.
All **51 decisions and 184 URL stops** persist.

Canonical tests pass **438 / nine optional skips**. Full downloads reproduce
**14 source / 113 runtime outputs offline**; all 113 anonymous runtime bodies and
the actual preceding rolling seed match. Actual desktop/mobile checks cover all
306 reader frames, the entire current snapshot, DE/DC/SC counters, 14 existing
native-map cases and all nine model controls. Representative images were viewed.
The 33-directional/17-held comparison policy is unchanged.

**Nationwide intake is not finished.** DE/DC, ND, FL/NH and remaining genuine
source/history/model/boundary gaps remain open before the full audit THEN polish.
[Acceptance](../data/participation-access/20261115-de-dc-sc-automatic-intake-01/acceptance.json),
[all decisions and source holds](../data/participation-access/20261115-de-dc-sc-automatic-intake-01/observations.json) and
[both complete query-set downloads](DATA.md#de-dc-sc-automatic-intake).

## Verified current-source qualification

**The unattended pipeline now checks mixed-source estimate eligibility for
all 50 states plus D.C.** The added ledger records source population, registration
frame, election stage and endpoint compatibility before numerical updates.
It preserves the existing 33 directional House comparisons, 17 held comparisons
and 34 registered-frame scenarios. Source availability alone does not approve
new probabilities, survey fits, demographic turnout or local allocation.

Actual scheduled collector 43726706434 supplied source `4175130d`
at its truthful older producer `e2efb0bd`. Separately reviewed
estimate engine `85f55ce0` and website workflow
`66f245c9` produced runtime `a41c1024`
in hosted job 43740356899. This reuses automatic collection,
not manual election-result retrieval or a new website build.

The refresh contains **18,285 record appearances across 28 states**, not people
or complete county/precinct coverage. Montana has one fresh appearance instead
of two; all last-good Yellowstone records, including 63,982 native ballots and
their original clocks, remain unchanged. All 51 decisions and 184 URL stops persist.

The complete source/runtime downloads reproduce **14/113 outputs offline**;
all 113 anonymous runtime bodies and the real preceding rolling seed match.
Actual desktop/mobile checks pass every 306 reader frames, the full current
snapshot, nine model controls, 34 scenarios and 51 decisions. Both actual
screenshots were viewed. Frozen study probabilities, weights, fits, existing
qualification masks and every other model-query body remain unchanged.

**This is not nationwide precinct completion.** Historical integration and
genuine access, source-frame, identification and boundary holds remain open.
Finish substantive prerequisites, then the full audit, then usability polish.
[Acceptance](../data/participation-access/20261115-current-source-qualification-01/acceptance.json),
[all decisions](../data/participation-access/20261115-current-source-qualification-01/observations.json) and
[both complete downloads](DATA.md#current-source-qualification).

## Verified NC/UT automatic intake

**Utah now passes actual unattended hosted capture and data-only website delivery for four reviewed county totals**: Cache, Kane, Millard and Piute. The other
25 counties keep their independently qualified last-good observations and holds;
this is not statewide, precinct-complete or newly certified participation.
Each PDF retains its own printed clock with unknown timezone. API/upload clocks
are separate. Cache/Millard use agreeing embedded-text readers; Kane/Piute use
RapidOCR at two resolutions, the same engine rather than independent algorithms.
No registration denominator, turnout rate, boundary or model is newly approved.

**North Carolina's existing 100-county automatic intake is hardened, not new
coverage. Its required API remains source-stopped: zero fresh updates.**
The full prior body, selected queries, update vector and all 100 last-good county
counts/clocks remain intact. Coherent first-failure recovery and unselected
state-parent rollback guards pass. A shared archived export ID cannot route
Nebraska as North Carolina. The old duplicate NC dispatch is removed.

Source/engine `e2efb0bd` / collector 43725870163,
workflow `ce36ca7e` and runtime `a73df8b1`
/ job 43728465099 are verified. Advancing the engine pin records
the collection-dispatch change; numerical projector algorithms are unchanged.
The hourly GitHub pipeline updates qualified counts and compatible estimates
without assistant retrieval or a Pages rebuild. It does not refit unchanged
survey models or allocate demographic estimates to counties or precincts.

Actual granular refresh is **18,286 record appearances across 28 states**,
not people or complete local coverage. The refresh-appearance changes from the preceding accepted collection are MT +1, UT +4; these are not additional people. All **51 decisions and 184
URL stops** persist. Unchanged canonical code suite: **465 passed /
9 optional skips**. Both full downloads reproduce
**14 source / 113 runtime outputs offline**; all 113 anonymous runtime bodies and
the actual preceding rolling seed match. Actual desktop/mobile checks cover all
306 reader frames, the full current snapshot, every NC/UT county detail, unknowns
versus zero, 14 existing native-map cases and all nine model controls.
Representative actual images were viewed.

**Nationwide intake is not finished.** Genuine source-access, extraction,
historical, model and boundary gaps remain open before the full audit THEN polish.
[Acceptance](../data/participation-access/20261115-nc-ut-automatic-intake-01/acceptance.json),
[all decisions and holds](../data/participation-access/20261115-nc-ut-automatic-intake-01/observations.json) and
[both complete query-set downloads](DATA.md#nc-ut-automatic-intake).

## Verified ID/RI automatic intake

**Rhode Island now passes actual unattended hosted capture and data-only website delivery for all 40 reviewed source slots**: 39 municipalities plus the separate Federal reporting
unit. Federal is not allocated to towns or precincts. The native statewide zero
is an unqualified backend placeholder, not observed statewide turnout; no
locality sum is promoted to a new statewide count or analytical rate.

**Idaho remains source-stopped: zero fresh updates.** Its complete last-good
count shard, 44 county parents, 986 separate reporting units, native geometry,
qualification masks and original clocks remain exact. County and unit frames
are not additive populations. The retained authority identifies the November 3,
2026 **general election**, not a primary. Twin Falls' registration discrepancy
stays held; the workbook's own clock stays unknown, not borrowed from its parent.

Both adapters guard every locality against rollback from the last successful
capture while using frozen registration templates. Complete prior pin/query/
update validation, partial rollback, malformed source, true zero and repeat
cases pass. Controlled revised inputs are tests, not new publisher observations.
The hourly GitHub pipeline updates qualified counts and compatible estimates
without assistant retrieval or a Pages rebuild. It approves no new rate, map,
demographic turnout, allocation or survey fit; the 33-directional/17-held
comparison policy is unchanged.

Producer `ee9b9cca` / collector 43715085278,
unchanged engine `2e0e2507` / workflow `6cd0fdc4`
and runtime `67db0820` / job 43716771839 are verified.
Actual granular refresh is **18,281 record appearances across 27 states**,
not people or complete local coverage. A temporary Yellowstone County source
failure is not counted as fresh; its last-good observations and clocks stay exact.
All **51 decisions and 184 URL stops**
persist. Canonical tests: **453 passed / 9 optional skips**.
Both full downloads reproduce **14 source / 113 runtime outputs offline**;
all 113 anonymous runtime bodies and the actual preceding rolling seed match.
Production checks cover all 306 frames, the full current snapshot, every ID/RI
parent/unit detail, 14 existing native-map cases and all nine model controls
at desktop/mobile widths. Representative actual images were viewed.

**Nationwide intake is not finished.** Stopped feeds and remaining genuine
source, historical, model and boundary gaps remain open before the full audit
THEN polish. [Acceptance](../data/participation-access/20261115-id-ri-automatic-intake-01/acceptance.json),
[all decisions and holds](../data/participation-access/20261115-id-ri-automatic-intake-01/observations.json) and
[both complete query-set downloads](DATA.md#id-ri-automatic-intake).

## Reviewed Utah and North Carolina adapters

The collector also routes the four existing Utah county totals for Cache, Kane,
Millard and Piute to the official API-declared summary PDFs. The measure is the
literal **Ballots Cast - Total**, not candidate votes or a registration stock.
The other 25 counties remain held. Each report retains its own printed local
clock with an unknown timezone; API clocks are separate context. Registrations
and printed percentages are not promoted to analytical denominators or rates,
county totals are not added into a statewide result, and existing map and
completion qualifications are preserved.

Cache and Millard require agreeing PyMuPDF/pdfplumber embedded-text reads.
Kane and Piute use pinned RapidOCR at two resolutions: these are **the same
engine, not independent algorithmic validation**. Exact election/county/measure
labels, agreeing selected counts and the confidence threshold remain required.
Malformed or ambiguous inputs retain the whole last-good four-report family.

North Carolina's existing 100-county `bct` reported-ballot family now has a single
prior-aware route instead of duplicate legacy collection. Its full query still
requires the statewide control and all 100 counties to reconcile. The 403 other
NC observations and early/mail frames are not replaced or added. The exact
official URL remains source-stopped; this adapter must open no transport while
that policy applies. A coherent first-attempt outage can recover on a later
permitted valid response, but corrupted priors and county or unselected-state
clock/status rollbacks reject the complete successor.

Both adapters use frozen registration templates and validate the last successful
capture's complete pin/query/update vectors. Their source fixtures and portable
tests are included in the complete source ZIP. This describes reviewed adapter
capability, not fresh acquisition, hosted delivery, a new fit or nationwide
completion; those require their own actual acceptance.

## Reviewed Idaho and Rhode Island adapters

The default collector also routes the existing Idaho and Rhode Island slots to
their reviewed official products. This is source-adapter capability, not a claim
of fresh acquisition or website activation. Idaho's required API is already in
the durable stop policy; it must remain unrequested and retain its last-good
counts, native maps and original clocks.

Idaho's retained report explicitly identifies the **November 3, 2026 general
election**, with `isPrimary=false`; older descriptions calling this product a
primary are incorrect. Its 44 county parents and 986 reporting units are separate
complete representations, not additive populations. The county/API and workbook
registration disagreement in Twin Falls remains held. Existing denominator and
map qualifications are preserved, not newly approved. Workbook rows have no
established own update clock: their clock stays unknown, while the separate
parent API clocks remain explicitly labeled context.

Rhode Island retains all 39 municipalities plus the separate Federal reporting
unit. The native statewide zero remains an unqualified backend placeholder;
neither it nor a derived locality sum becomes statewide turnout. Federal counts
remain unallocated, registration is not promoted to an analytical denominator,
and existing geography/reference holds survive. Explicit native `Z` clocks
retain UTC.

Both adapters compare each locality's source clocks against the last internally
consistent successful capture, not just the frozen registration templates.
Idaho additionally checks each county's last-updated clock and official-status
regressions. A partial rollback, malformed source or incoherent prior query
rejects the whole successor and retains the complete prior data and clocks.
Literal zero remains distinct from missing or unknown. Full numerical queries,
portable tests and fixtures travel in the complete source package; hosted and
live delivery require separate acceptance.

## Reviewed Delaware, D.C. and South Carolina adapters

The default collector now connects Delaware's declared 2026 turnout JSON,
D.C.'s election declaration, voter summary and full participation CSV, and
South Carolina's statewide statistical announcement. These are bounded producer
capabilities; hosted capture and live activation require separate acceptance.

Delaware refreshes its one existing statewide observation. The complete query
retains the statewide row and all 41 representative-district contexts, with
district counts and registrations checked against the state controls. Those
contexts do not become new county/district/precinct slots or map approvals.
The source supplies no turnout update clock; candidate/cache timestamps are not
substituted. Literal official status may advance but must not roll back.
The numerical runtime also refreshes the separate visible statewide mirror only
when its entire prior view matches one canonical state observation and the
successor preserves that observation's identity. Unmatched reviewed rows remain
unchanged; canonical count updates cannot silently leave the matched sidebar
counter on its old value. This does not select statewide data as county coverage.

D.C. refreshes its one existing citywide observation only after the two literal
participation contests, full 144-unit identity inventory, source registration
and ballot totals reconcile. Candidate votes are not turnout. The election's
native UTC update clock is checked for rollback. Separate September registration,
early voting and received-mail reports are neither substituted nor added.
Existing provisional/reference qualifications and map holds remain unchanged.

South Carolina refreshes only the existing current-snapshot statewide
source-defined participation count. Statistical labels, complete mode components,
literal printed percentages and full selected factual queries are validated.
Printed percentage disagreements remain unrepaired. The unsupplied exact
registration stock, analytical rate, count clock, timezone and reporting counters
remain unknown; publication/certification dates do not fill them. Prior native
statistics are retained as historical provenance, not left as the current query.

All three adapters preserve existing identities, views, literal measures and
qualification holds, retain last-good values after failure, and export complete
factual queries with portable tests. No new local coverage, demographic turnout,
geographic join, model fit or nationwide-completeness claim follows from them.
South Carolina's current-snapshot projection changes the numerical runtime engine
and therefore requires a deliberate consumer engine-pin delivery.


## Verified VA/ND/LA delivery

Virginia's 133 reviewed locality parents and Louisiana's newly onboarded
3,783 observations now pass actual hosted collection, complete offline replay
and production acceptance. North Dakota's implemented adapter is source-stopped:
its required full-data feed was denied and was not retried. Its 53 county parents,
358 source-unit rows, native map, counts and original clocks remain last-verified,
not fresh. The entire North Dakota count and native bodies remain byte-identical.
Source `38bda148`, collector 43704470689, engine
`38bda148`, runtime `a8ec8461`
(job 43705844196) and workflow `a8d7b4b7` are pinned.
The hourly source/consumer workflows update qualified counts and compatible
estimates without assistant retrieval or a Pages rebuild for each report.

The actual collector refreshes **18,242 record appearances
across 26 states**, not unique people, disjoint populations or
nationwide local completeness. Louisiana preserves all 258 older observations
and their modes; new rows enter only the official view: 64 parish parents,
3,718 precinct rows and one unselected state control. Its literal **# VOTING**
is source-defined participation, not candidate votes or independently qualified
physical ballots/unique people. Missing clocks/counters remain missing.
Virginia uses locality `ballotsCast`, not precinct `voterTurnout`.
North Dakota keeps native ballot buckets separate from House candidate votes.
No new rate, map, geographic join, survey fit or 33-directional/17-held
comparison qualification is inferred.

Canonical validation passes **397 tests**, with nine optional skips. The complete
source/runtime downloads reproduce all **14/113 outputs** offline, with zero
requests; all 113 anonymous runtime bodies and the actual preceding rolling seed
match. Desktop/mobile production checks cover all 306 count frames per width,
every selected LA/VA/ND parent/unit detail, preserved native maps and all nine
model controls. Eight representative images are physically reviewed and hash-bound.
All 51 decisions and 182 durable URL stops persist.

**Nationwide county/precinct intake is not finished.** Remaining source,
historical, model, boundary and held-extraction gaps stay open before the full
audit THEN beautification. Source failures retain last-good values and clocks.
North Dakota's automatic-refresh child remains blocked, not completed.
[Acceptance](../data/participation-access/20261115-va-la-nd-automatic-intake-01/acceptance.json),
[all 51 decisions and source holds](../data/participation-access/20261115-va-la-nd-automatic-intake-01/observations.json),
[both complete query-set downloads](DATA.md#va-nd-la-automatic-intake), and
[earlier access-policy receipt](../data/participation-access/20261115-louisiana-access-stop-01/observations.json).

## Reviewed Louisiana post-election onboarding

The default registry binds the reviewed official navigation and publisher-script
evidence to the exact statewide and parish workbook routes. Without that complete
authority declaration, onboarding is held. A successful capture adds 3,783
source-defined observations: one unselected state parent, 64 parish parents and
3,718 precinct rows. The 258 saved early/mail observations remain unchanged;
new local rows enter only the official view.

The literal measure is **# VOTING**, not candidate votes, independently verified
unique people or automatically qualified physical ballots. Source registration
stocks remain context; analytical rates and new map joins are withheld. Missing
source clocks and reporting counters remain missing. Repeated collection preserves
identities; revised counts use the same validated projection and failures retain
last-good values.

## Reviewed North Dakota native ballot adapter

The reviewed election-348/House-22055 family refreshes 53 county parents and 358
source units from the full-results, election and turnout JSON products. Explicit
native ballot buckets and county/state controls reconcile independently of House
candidate votes, which are consistency checks only. Legacy county ordinals are
not FIPS codes. Existing 338 map joins, 20 geometry holds and all held rates remain
unchanged. Native projection requires matching complete prior vectors and exact
source lineage, including on subsequent updates.

These are producer capabilities, not claims of successful hosted acquisition or
live activation. Accepted delivery receipts identify the actual deployed scope.

## Reviewed Virginia native locality adapter

The collector supports the 133 already reviewed Virginia locality parent
observations from the official 2026 general-election JSON family. The exact
state root and all 133 reviewed locality URLs are source-identity pinned.
The parent projection uses each locality election's literal `ballotsCast`;
it never substitutes precinct `voterTurnout`, candidate votes, a locality
sum for the statewide zero, or pooled voting modes.

The complete native query retains all 2,529 precinct rows, including both
`ballotsCast` and `voterTurnout`, registrations, UUIDs, names, reporting
vectors and distinct source clocks. Precinct registrations reconcile to
locality and statewide `totalVoters`, but remain unqualified rate context.
The statewide `ballotsCast=0` is retained as an unqualified control.
Existing early/mail/history frames, all geographic joins and every rate hold
remain unchanged. The separate 710-row mapped native layer is verified
against `ballotsCast` but is not rewritten by this source-only integration;
the other 1,819 native units remain held.

This adapter is a producer capability, not a claim of hosted collection,
runtime activation or website acceptance. Those require separately pinned
complete packets and live acceptance.

## Reviewed Oregon county turnout adapter

The collector supports the 36 already reviewed Oregon county observations using
the current turnout API declared by the official turnout page's own scripts.
It retains the complete native county records and independently verifies the
page's election date, count labels, county identities, statewide ballot count
and active-registration total. The initial exported frame and stable identities
are checksum-bound; later updates must retain matching native vectors and
non-regressing county count clocks.

`calcVoterTurnout` is the native **ballots counted** field, not candidate votes.
Native `IsReported=false` and ancillary zero counters do not erase positive
counts or establish completion. County timestamps have no supplied timezone;
the separate statewide `PT` label is not assigned to county clocks. Zero is
distinct from missing or malformed input, which retains the last accepted data.
Source status may change from unofficial to official without qualifying a new
rate, map join, unique-voter count or certification.

Only the reviewed county frame is refreshed. Saved mail/early frames and older
state observations are separate appearances, never added or silently relabeled.
This adapter does not by itself establish live deployment: the accepted delivery
records and complete downloads below identify what has actually been activated.

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
Exact duplicate feed payloads may reference their full granular-state entry.
Collection, recovery and publication validate the alias target and checksum;
repacking an already compact state is idempotent.

Granular source facts are stored once in the complete
`granular-source-queries.json.gz` query. The bounded snapshot retains exact
checksum-bound references, source metadata, scalar qualifications and update
inventories. The runtime verifies and restores the complete facts before count
projection or estimation; a missing query, changed checksum or mismatched
inventory stops activation. No query rows are dropped to meet the size limit.

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
python3 -m pytest -q tests/test_results_intake.py tests/test_results_granular.py tests/test_results_native.py tests/test_results_native_state_family.py tests/test_results_native_workbooks.py tests/test_results_pdf_tables.py tests/test_results_json_statistics.py tests/test_results_pdf_boston.py tests/test_results_pdf_periodic.py tests/test_results_pdf_affiliations.py tests/test_results_pdf_jefferson.py tests/test_results_pdf_cass.py tests/test_results_native_cass.py tests/test_results_pdf_dunn.py tests/test_automatic_native_refresh.py tests/test_nationwide.py tests/test_current.py
```

## Separate reference/count dependencies

The runtime producer revalidates every mapped observation against its complete
canonical preimage and preserves every held source identity before updating a
separate reference layer. It refreshes the exact count-shard byte length/hash
and all native display fields together; geometry, reference-only map approval,
held units and withheld rates do not change.

The same complete-observation checks allow repair of stale derived metadata
when no new count changes arrive. Production testing of runtime `956242c7`
exposed an old Jefferson shard pin and a missing new source-hash display field;
the browser correctly rejected that layer. The producer repair passes the
unchanged browser contract for all 529 mapped and 117 held observations.
Hosted successor runtime and production acceptance are separate delivery gates.

## Arkansas, Arizona and Wyoming native-unit sources

The shared source planner includes the 2,768 accepted Arkansas reporting units,
1,763 Arizona reporting units across all 15 county APIs, and 432 Wyoming
reporting units. These are parser capabilities, not a claim that every future
source is discoverable or that hosted/live delivery has passed.

Arkansas reads the reviewed full native turnout export, not its application
shell. Native county/precinct IDs are checked against the complete accepted
inventory. Where the body supplies no labels, retained accepted labels remain
explicitly identity context, not newly observed native labels. Missing ballot
or registration cells remain unknown and may become reported in later
snapshots; a true zero remains zero. The reviewed download asset does **not**
establish a stable successor-export discovery route. That discovery gap remains
an explicit hold; no endpoint is guessed.

Arizona uses literal county/precinct UUIDs and the public root declaration to
reconcile precinct, county and registration totals. A zero in the statewide
backend is not substituted for positive county observations. Positive
statewide totals that reconcile to the declared county totals are
accepted when that backend zero is corrected. Duplicate locality UUIDs are
rejected rather than overwritten. Only supported
literal UTC clocks are assigned UTC; malformed clocks and rollbacks are
rejected. January 2027 updates still refer to the declared 2026 election.
Explicit boolean official-status changes in Arkansas or Arizona are retained
as source status, not promoted to certification or analytical-rate approval.

Wyoming reads the direct Total Ballots Cast workbooks, checks the exact 2026
general-election/OFFICIAL headings and all 23 county/state parent controls,
and retains candidate/write-in/overvote/undervote accounting only as a check
against direct ballot counts. Candidate totals are not substituted for ballots.
No registration denominator or result clock is invented.

All three adapters preserve existing observation identities, geography and
rate/measure holds. Complete native queries and replay inputs remain in the
download; no new boundary matches, rates or behavioral fits are authorized.

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

The Cass County, Indiana cumulative-report adapter refreshes its existing
turnout-display observation, not cast ballots. It checks every page's election,
county, edition, clock and columns. The printed registration reference remains
context, not an analytical denominator; the simultaneous unofficial/official
literals, partial reporting and unknown timezone remain explicit. Neither a
FINAL filename nor a reporting fraction establishes certification.

Dunn County, Wisconsin uses a separately reviewed source-URL correction: its
accepted count and original-file hash identify the unofficial report, while
both stored URLs incorrectly named the distinct official report. The initial
correction requires the complete prior-row hash and retained original-file hash.
Later updates must preserve the same identity and strict measure/status contract.
The official report remains a separate control, never a contest-vote fallback;
the absent count clock and held rates remain absent and held. Complete packets
include both adapters, portable behavior tests and the safe Dunn fixture.
These are parser capabilities, not a claim of hosted or live acceptance.

The projector marks validated URL replacements as automatic refreshes, just as
it does ordinary updates. This producer-owned download marker binds the browser's
complete-analysis link to the current immutable runtime packet, retaining the
older download separately. It does not expand the source adapter's allowed
count, identity, clock, denominator or geographic changes.

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

## Verified Oregon county delivery

Oregon's **36 reviewed county observations** now refresh unattended from the
official page's declared turnout API. Collector 43691974826 at producer
`99504042` and runtime `01378416`
(job 43693287439) are accepted. The numerical engine `25239bca` is unchanged.
The two-file reader repair at `9b8d5979` (actual Pages job
43695104630) fixes a current-ZIP link that was stale when native
dataset contents were reused across a count-only update. No numerical engine
pin or source-model refit changed. This corrective reader build is not a build
per numerical activation; all 437 prior complete-download pins remain intact.

The actual collector refreshes **14,326 record appearances across 24 states**,
not unique people, disjoint populations or nationwide local completeness.
Oregon's complete native county query reports
**1,992,463 ballots counted** and
**3,109,123 active registrations**, matching its
independently parsed statewide header. **27 county count values** changed from
the previous saved frame; unchanged values remain present, not discarded.
`IsReported=false` and ancillary zeros do not erase positive native counts or
establish completion. Native county IDs are not FIPS. County clocks retain their
literal timestamps without an invented timezone; statewide `PT` remains separate.
Saved mail/early frames and older state observations are not added or silently
relabeled. All county analytical rates and geographic joins remain held.

Maintained 366 and canonical 372 tests pass. The actual complete source packet
passes 130 portable tests with nine optional original-file skips and reproduces
all 14 numerical outputs offline. The complete runtime packet reproduces all
113 outputs offline; all 113 anonymous public bodies, exact nested source and
actual preceding rolling seed match. Actual no-override desktop/mobile checks
cover every Oregon county detail/current full download, all 306 count frames,
all seven reporting tables (6,660 rows), the preserved native maps and all nine
model controls. Eight representative production screenshots are physically
reviewed and hash-bound. All 51 decisions and the numerical packet's 179 URL
stops persist. A later observed Florida HTTP 403 is separately persisted as the
**180th current URL stop**, without rewriting either numerical ZIP or treating
the retained November 6 Florida evidence as fresh data.

**Nationwide county/precinct intake is not finished.** Arkansas and Mohave holds,
Manchester ward OCR ambiguities, remaining source, multiyear, model and boundary
gaps remain open, before full audit THEN beautification. Separate private Florida
work is not included or claimed live in this acceptance.
[Acceptance](../data/participation-access/20261115-oregon-county-automatic-intake-01/acceptance.json),
[all 51 decisions and source holds](../data/participation-access/20261115-oregon-county-automatic-intake-01/observations.json), and
[both complete query-set downloads](DATA.md#oregon-counties-automatic-intake).


## Verified native JSON delivery

Native-source JSON intake and the reporting-table reader are verified through
collector **43682681316**, producer/engine `25239bca`,
runtime `ed6113f1` (job 43684173907) and
frontend `a4ff8b0a` (actual Pages job 43688125297).
The collector refreshes **14,290 record appearances across 23 states**,
not unique people, disjoint populations or nationwide local completeness.
This increment refreshed **1,738 Arizona reporting units across 14 county APIs**
and **432 Wyoming units**; one additional Montana record refreshed compared
with the prior run. Arkansas remains source-stopped; Mohave's 25 Arizona
units remain on a source-schema/semantic hold. Both retain accepted counts and
their original clocks. All 51 jurisdiction decisions and 179 URL stops persist.

The actual browser's AR/AZ/WY reporting-table rejection is repaired with strict
source, identity, complete-vector, count, clock and held-rate checks. All seven
reporting tables (6,660 rows) now load. Alaska's 523 and Hawaii's 496 rows are
separately keyed, immutable **saved** exports, not new automated collectors.
Unknowns remain distinct from zeros; pooled, overseas and mode-specific units
are not residential precinct allocations. No new turnout rate, boundary join,
source-model refit or certification is inferred.

Maintained 360 and canonical 366 tests pass. The actual complete source packet
passes 124 portable tests with nine optional original-file skips and reproduces
all 14 numerical outputs offline. The complete runtime packet reproduces all
113 outputs offline; all 113 public bodies, nested source and actual preceding
rolling seed match. Actual no-override desktop/mobile checks cover all 306 count
frames, all seven tables, current plus original downloads, the preserved
KY/IN/MA/NM/MN maps and all nine model controls. Reviewed production images are
hash-bound. The actual Pages payload (994,246,111 bytes) and tar
(996,843,520 bytes) both remain below 1 GB; all 437 prior complete
downloads and all unrelated/scope bodies are preserved. Numerical updates
activate counts/native data/compatible estimates atomically without rebuilding
Pages; the one-time build here repairs the reader.

**Nationwide county/precinct intake is not finished.** Historical, source,
model and boundary gaps remain open, before full audit THEN beautification.
[Acceptance](../data/participation-access/20261115-native-json-automatic-intake-01/acceptance.json),
[all 51 decisions and source holds](../data/participation-access/20261115-native-json-automatic-intake-01/observations.json), and
[both complete query-set downloads](DATA.md#native-json-automatic-intake).


## Verified Cass/Dunn delivery

Cass County, Indiana and Dunn County, Wisconsin are verified through
collector 43676304421 at producer `2fa2b159`,
engine `ec838082`, consumer `7b2cdcf4` and
runtime `1b0bdc1f` (job 43677587999).
Two existing county observations now support unattended revised-report extraction;
the accepted counts remain 9,699 and 19,896, not newly discovered participants.
The actual collector refreshes **12,119 record appearances across 21 states**,
not unique people, disjoint populations or nationwide local completeness.

Cass retains its literal turnout-display numerator, separate registration
reference, partial reporting, simultaneous unofficial/official text and unknown
timezone. It is not promoted to cast ballots or a new analytical turnout rate.
Dunn's accepted original and count identify the unofficial report; the prior
stored URLs incorrectly named the separate official report. A pinned reviewed
bridge corrects only those URLs, while the projector supplies the automatic
download marker. Its missing count clock, held rates and geographic hold remain.
The official report is a control, never a candidate-vote replacement.

Maintained 326 and canonical 332 tests pass. The actual complete source packet
passes 49 portable tests with nine optional original-file skips and reproduces
all 14 numerical outputs offline. The complete runtime packet reproduces all
113 outputs offline; all 113 public bodies, nested source packet and actual
preceding rolling seed match. Actual desktop/mobile checks cover both county
details and current full-download links, all 306 reader frames, the preserved
KY/IN/MA/NM/MN maps and all nine model controls. Reviewed screenshots are
hash-bound. All 51 decisions and 178 source stops persist. No private survey
refit, new rate, geometry change or static Pages build occurred.

Broader source, historical, model and boundary gaps remain open, before full
audit THEN beautification. The private next JSON-family patch is not included
or claimed live by this acceptance.

[Complete acceptance](../data/participation-access/20261115-cass-dunn-automatic-intake-01/acceptance.json) and
[all jurisdiction and native-source queries](../data/participation-access/20261115-cass-dunn-automatic-intake-01/observations.json);
[both complete downloads](DATA.md#cass-dunn-automatic-intake).


## Verified county/unit delivery

Oklahoma's in-person-early PDF and Jefferson County, Kentucky's precinct
statistics are verified through producer `8e72a462`,
collector 43670260974 and runtime `d051a6cb`
(job 43672808862). These two products refresh **723 existing
records**: all 77 Oklahoma counties and 646 literal Jefferson units. Their
current counts agree with the previously accepted counts; this connects
unattended revised-report extraction rather than inventing new participation.
The full collector refreshes **12,118 record appearances across 21 states**,
not unique people, disjoint populations or nationwide local completeness.

Oklahoma remains early-only: its 186,488 printed state parent is a control,
not a new all-method observation. Fourteen absent affiliation cells stay
unknown; printed zeros remain zero, and affiliation is not candidate choice.
Jefferson preserves all 60 suffix labels and 19 zero totals, all repeated
page contexts and the native clock. Its separate county parent is unchanged;
Mail is not returned envelopes and 646/646 is not certification.

The first hosted run, 43669246178, withheld Jefferson correctly: an unbounded
dependency installed pypdf 7.1.0, whose extracted header differs. Cache-only
Linux diagnosis 43669998932 reproduced the failure with zero source requests.
The collector and PDF extras now pin reviewed `pypdf==6.16.0`; election,
column, inventory, clock and numerical guards were not relaxed. Original
failed-family evidence remains. Maintained 272 and
canonical 278 source tests pass.

Production testing of the first runtime `956242c7` exposed stale separate-
reference metadata: an old count-shard pin and a missing source-hash field.
The browser correctly withheld that layer. Engine `d01dccf4`
revalidates every full observation and held identity before rebinding;
it also repairs that active input when no count changes arrive. Its
281 maintained and 287
canonical tests pass. The unchanged browser validator and all 14 geometry
bodies remain intact; original failed-runtime evidence is retained.

A separate asynchronous-loader regression found that current-download link
decoration changed the full records used for strict reference comparison.
Frontend `54956bb7` validates the original checksum-verified
full count shard instead. The strict reference validator and download
decoration remain unchanged. All 38 focused tests, the complete count
contract command, exact build, whole-runtime loader and ten built-page
map cases pass. Actual Pages 43673824614 and its source guard
pass: 994,240,640 payload and 996,843,520 tar bytes,
both strictly below one billion; all 437 prior full-download pins and
actual served bodies match. Independent older canonical website sources
are preserved beside the exact published source snapshot.

Complete source/runtime packets reproduce 14/113 outputs offline with zero
requests; all 113 public runtime bodies match. Actual desktop/mobile checks
cover all 723 new records, all 306 reader frames, Jefferson's 529 reference
joins and 117 holds, preserved IN/MA/NM/MN maps and all nine model controls.
Screenshots are physically reviewed and hash-bound. All 51 decisions and
prior stops persist; no geometry, rate or private survey fit changes.
Numerical activations still require zero static builds. A pin-only consumer
selects the repaired engine; a separate tested frontend code deployment
corrects canonical-reference loading without changing count-download links.

There are still 20 reported but unadapted source captures across
8 states. Manchester handwriting remains
numerically held after both RapidOCR and native macOS Vision proved unreliable;
an unchanged-hash count lookup is not revised-count automation. Broader
source, historical, model and boundary gaps remain open, before full audit
THEN beautification.

[Complete acceptance](../data/participation-access/20261114-county-unit-automatic-intake-01/acceptance.json),
[all jurisdiction decisions](../data/participation-access/20261114-county-unit-automatic-intake-01/observations.json) and
[both complete downloads](DATA.md#county-unit-automatic-intake)
retain the evidence and limitations.


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
