# Voter-participation source ledger

Last reviewed: 2026-11-09 UTC.

**Start here:** [Overview](README.md) | [Estimation methods](METHODOLOGY.md) |
[Complete downloads](docs/DATA.md) | [Reproduce](docs/REPRODUCING.md).
This document is the detailed reference ledger, not the methods introduction.

| Reference area | Jump to |
|---|---|
| Historical demographic/state frames | [Every-state groups](#every-state-historical-demographic-participation), [CPS](#historical-cps-group-registration-and-response-frames), [EAC](#held-eac-historical-state-controls-complete-verified-publication) |
| Administrative counts and registration | [Primary sources](#primary-administrative-data-and-population-denominators), [historical controls](#historical-administrative-participation-comparison), [Wyoming registers](#wyoming-declared-registration-reports-and-source-weighted-scenarios) |
| Candidate returns and context | [Historical compilations](#historical-returns-academic-and-publisher-compilations), [2026 counts](#current-2026-returns-exact-counts-and-comparison-products) |
| Survey definitions and current analyses | [Studies](#surveys-participation-histories-and-vote-choice-evidence), [derived outputs](#current-derived-analyses-and-remaining-reconciliation) |
| Collection rules and access holds | [Source classes](#status-and-source-classes), [access](#access-methodology-and-paidreference-only-leads), [automation](#automation-contract) |
| Website acceptance records | [Short Methods and GitHub docs](#website-methods-and-github-documentation), [source-backed navigation](#website-repair-source-backed-navigation-and-precinct-coverage) |

This is the canonical **source-family ledger** for the research project and its
[companion website](https://github.com/hanshanley/margin_of_error). It includes
primary data, official compilations, academic harmonizations, secondary feeds,
user-supplied studies, and methodological references. An entry does not imply
complete coverage, independent validation, or permission to redistribute originals.

The per-file URLs, native timestamps, retrieval receipts, and checksums remain in
the machine-readable inventories linked below. Those inventories, not a copied
list of thousands of county URLs, are the inputs for future automation.

## 2026 statewide demographic participation models

[Complete 2026 state/group inputs, code and results](https://github.com/hanshanley/margin_of_error/releases/download/participation-civic-state-demographics-20261108-01/complete-analysis.zip):
671 coarse source-weighted model estimates and all 1,530 query decisions.
All 50 Civic source states have an overall estimate; D.C. has no source sample.
Age, education, source sex, race/Hispanic origin, native income and source
county context are separate dimensions. The native LIKELYVOTER classification
is a model, not administrative turnout, observed staying home or a 2024 CPS
projection. No registered/eligible group populations or local allocations.

Full CHEP_WEIGHT group denominators are retained, without fitting or scaling.
Unknowns stay in the statewide frame. Sparse and complementary cells are held
within states and across states, preserving the prior pooled-source release.
No isolated race code88 or small GENDER3 cells are exported. Source-support
screens are not precision/anonymity guarantees; design intervals, field period,
population calibration and state representativeness remain unqualified.
Income is not independently qualified household income; RUCC is county context,
not individual residence.

Immutable release `438581821` has four full byte-verified assets; ZIP
276,432 bytes / nine members / SHA-256
`59c0745c5975642be580d95511eecb8520637b34a7de83423232780f6bb7f227`.
Five tests, 28,496 independent native-aggregate/Fraction/disclosure/package
checks and two exact blocked-network/external-execution reproductions pass.
Maintained `scripts/civic_state_groups.py` reproduces all public queries.
Original 113,020-case verification is reused, not rerun. No raw respondents,
private fine cells or choice tables. Website integration and the requested
post-integration project audit are now complete for this increment.

Live website `5005b2e` / Pages `42534719520` / artifact `13638962850` /
deployment `7643472553` passes all 36 production configurations. Every 1,530
2026 decision and 1,734 historical state/group rate is checked on desktop/mobile.
All prior links, IDs, 436 complete routes, native preview and source pin survive.
Actual downloaded content/tar: 981,327,119 / 983,838,720 bytes, both below the
strict limit. The [concise audit](docs/AUDIT.md) records 9,092 additional checks,
including positive-cell complementary suppression and ten source absences.
Broader observed-demographic, population-frame and precinct gaps remain open.

## Connecticut dated active-registration frame

[Complete version-14 controls and native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-14/complete-analysis.zip)
add the [official October 19 registration report](https://portal.ct.gov/sots/election-services/statistics-and-data/voter-registration-and-enrollment-statistics).
Its native statewide `Totals Active` parent is **2,255,397**; inactive
234,553 and combined total 2,489,950 remain separate. This is a dated
snapshot, **not an election-time denominator** or a population validation.
All 169 towns, 15 count columns and eleven minor-party legend entries are
preserved. Affiliation is registration accounting, not party voting.
Source county/district literals do not establish geographic crosswalks.

The separate results feed's reported registration total 2,102,250 still
includes thirteen zero-registration / fourteen zero-voted towns. Both
52337/52338 versions and their original bytes remain unchanged. Agreement
with reported town sums does not resolve coverage or registry/mode semantics;
zeros are not zero populations. The October 19 snapshot does not repair
these results. Native statewide ballots/residual and new rate/map approval
remain withheld.

Conditional 1,229,441.05 participant / 1,025,955.95 nonparticipant
**dated-active units** assume unvalidated Civic-to-snapshot transport, not
observed staying home or town/group populations. Version14 retains all
51 state/D.C. rows, 30 control dispositions and nineteen scenarios.
Eleven tests, 4,651 independent checks, a third PDF extractor and two
byte-identical blocked offline reproductions pass. All 2,550 count cells,
town sums and native row equations reconcile; all fifty unaffected states,
eighteen prior frames and 29 prior controls are preserved.

The complete 102,374,460-byte / sixteen-member ZIP includes the original PDF,
both frozen independent extractions, selected factual results originals,
version13 baseline, maintained readers, optional extraction-refresh code,
tests, queries and checksums. PDF refresh requires PyMuPDF/pypdf; frozen-input
analysis is standard-library offline. Compiled application code and private
respondents are excluded. SHA-256:
`96c223b86f535d11c73d2134e3788a3451d820aef1003bef1e918af8c3f9e4f7`.
Earlier releases and the accepted website remain unchanged.

## Utah dated active-registration frame

[Complete version-13 controls and sufficient numerical inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-13/complete-analysis.zip)
reuse the held [Utah numerical query](https://github.com/hanshanley/margin_of_error/releases/tag/voter-county-utah-native-statistics-20261106-01).
The native statewide `Total active` parent is 1,784,255, dated
**November 2, 2026**, with no time or timezone. This is a dated active-register
scenario, not an election-time denominator for November 3 or a replacement
for any separate county-report denominator.

Native inactive 314,971 and combined total 2,099,225 remain unchanged:
active plus inactive exceeds the printed combined total by one. Both native
parent arithmetic discrepancies are preserved, not repaired or allocated.
All ten state and 228 county affiliation rows remain registration accounting,
not party votes, party turnout or modeled group participation.

All 29 prior county participation rows and their denominators remain
byte-identical. The 26 reports, nineteen counted-ballot snapshots (eighteen
with same-report registrations), six scope holds, four missing reports,
distinct Davis snapshots, Wayne
discrepancy and unqualified backend-zero fields remain in the full input.
No dated registration is substituted into those county observations.
Native statewide ballots and native-minus-model remain null; no state rate,
map, counting completion or population validation is approved.

Conditional dated-active units are 1,133,689.62 modeled participants /
650,565.38 nonparticipants under unvalidated snapshot/Civic exchangeability,
not election-time people or observed staying home. Register/cohort timing,
survey calibration and field period remain unqualified; no demographic
populations, local allocation or design interval is claimed.

Immutable release `438718321` has ten full byte-verified assets. The
101,997,925-byte / 17-member ZIP contains the complete permitted native
**numerical** input package, accepted version-12 baseline, every new query,
maintained code, unchanged Washington shared helpers and eight focused tests.
Raw operational/personnel worksheets remain excluded. 197 independent dated-
parent/Fraction/preservation/package checks and two blocked, byte-identical
offline reproductions pass. Maintained `scripts/utah_dated_register.py`
exports 51 state/D.C. rows, 29 source-control disposition records and eighteen
conditional frames. All 50 unaffected states, seventeen prior frames and 28
prior controls survive. No source acquisition, completed PDF/OCR/workbook/
private-survey reduction or website campaign was repeated.

## South Dakota derived complete-county registration frame

[Complete version-12 controls and sufficient native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-12/complete-analysis.zip)
reuse the held [native South Dakota query](https://github.com/hanshanley/margin_of_error/releases/tag/voter-precinct-south-dakota-20261105).
The 628,563 registration frame is **derived from all 66 county API parents**,
not a native statewide field. Each county's `Voters` is counted once, with
exact county-ID and literal-label coverage against the official cached
2026 turnout facts. The 12 declared `(Vote Center)` suffixes are retained,
not fuzzy aliases. Repeated vote-center/precinct registrations are not summed.

The separate county `calcVoterTurnout` sum 310,298 is diagnostic, not a selected
native statewide ballot reference. Native statewide ballots, turnout and
native-minus-model remain null. All 671 earlier reporting-unit gzip bytes,
596 available / 75 held unit-rate decisions, duplicate labels and vote-center
qualifications are unchanged; no new state rate or map is approved.
Native county `CurrentDateTime` is retained literally, but its clock meaning
and timezone are unqualified. County reported flags do not certify completed
counting; neither retrieval time nor that field becomes an update clock.

Conditional derived-register units are 296,578.40 modeled participants /
331,984.60 nonparticipants under unvalidated county-frame/Civic exchangeability.
The denominator basis, scenario units and source kind explicitly identify the
derived frame, despite retaining the legacy `native_registered_denominator`
CSV column for compatibility. Register status/cutoff, survey calibration,
field period and population transport remain unqualified. No observed staying
home, group populations, local allocation or design interval is claimed.

Immutable release `438706606` has nine full byte-verified assets. The
101,893,785-byte / 16-member ZIP contains the complete native query, accepted
version-11 baseline, every new query, maintained code, unchanged Washington
shared helpers and eight focused tests. 1,280 independent county/clock/
Fraction/preservation/package checks and two blocked, byte-identical offline
reproductions pass. Maintained `scripts/south_dakota_county_frame.py` exports
51 state/D.C. rows, 28 source-control disposition records and seventeen
conditional frames. No native statewide parent or ballot reference is added.
All 50 unaffected states, sixteen prior frames and 27 prior controls survive.
No source acquisition, completed candidate/workbook/HTML/private-survey
reduction or website campaign was repeated.

## Alaska native federal participation and overseas scope

[Complete version-11 controls and sufficient native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-11/complete-analysis.zip)
reuse the held [native Alaska query](https://github.com/hanshanley/margin_of_error/releases/tag/voter-precinct-alaska-20261105).
The explicit federal House parent reports `b=215,906` ballots and `v=605,433`
registered; `t=213,009` candidate selections are not ballots. Senate `b/v`
agree. Governor headers have 215,776 ballots / 604,611 registered: the
130-ballot / 822-registration difference exactly matches the retained federal
overseas unit, not an inferred cohort or a reason to blend election scopes.

The source is uncertified, updated `11/04/2026 2:11 PM`, timezone undeclared.
Native `p=403` expected / `r=400` reported are counts, not percentages.
Export `format="2024"` is a schema marker, not the election year; the literal
election identity is Alaska 2026 General Election. All 523 reporting-unit gzip
bytes remain unchanged: 402 geographic, 120 pooled district and one federal.
All 221 ballot-accounting discrepancies and 63 ballots-exceed-registration
flags remain. No pooled/federal allocation, precinct rate, map, completed
counting or final ranked-choice outcome is approved.

Conditional source-register units are 291,012.21 modeled participants /
314,420.79 nonparticipants; native-minus-model is separately -75,106.21.
The numerical contrast assumes unvalidated Civic-to-register exchangeability,
not observed staying home or independent population validation. Register
status definitions, survey calibration, field period and population transport
remain unqualified. Generic cast-ballot/rate fields stay blank; no group
populations or design intervals are supplied.

Immutable release `438694717` has nine full byte-verified assets. The
100,091,036-byte / 16-member ZIP contains the complete native query, accepted
version-10 baseline, all 76 native contest headers, every new query, maintained
code, unchanged Washington shared helpers and eight focused tests. Other
contest headers remain unreviewed and nonadditive. 615 independent native/
scope/Fraction/preservation/package checks and two blocked, byte-identical
offline reproductions pass. Maintained `scripts/alaska_state_control.py`
exports 51 state/D.C. rows, 27 source-control disposition records and sixteen
conditional frames. All 50 unaffected states, fifteen prior frames and 26
prior controls survive. No source acquisition, completed candidate/CSV/
geometry/private-survey reduction or website campaign was repeated.

## Virginia registration-only parent and partial locality scopes

[Complete version-10 controls and sufficient native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-10/complete-analysis.zip)
reuse the held [native Virginia query](https://github.com/hanshanley/margin_of_error/releases/tag/voter-precinct-virginia-locality-counts-20261105).
The API explicitly reports statewide `totalVoters=6,494,441`; all 133 locality
and registration totals agree, including native active/inactive arithmetic.
The source-defined parent is not inferred from locality or precinct sums;
component reconciliation does not establish survey/population exchangeability.

The state `ballotsCast=0` conflicts with the locality sum 3,593,781. The original
zero stays in the source query; selected statewide ballots, turnout and
native-minus-model remain null. No locality sum repairs state ballots.
Every locality clock and native reporting-status vector is retained separately.
All 2,529 earlier precinct observation rows remain byte-identical: their
2,798,626 native turnout subtotal is partial, not statewide all-mode turnout.
All 69 locality/House residual scopes remain unallocated; rate/map/completion
holds are unchanged.

Unofficial native UTC clocks stay distinct: asOf
`2026-11-05T02:19:25.4373295Z`, lastUpdated `2026-11-04T23:28:02.0027742Z`
and publishDate `2026-11-05T02:19:26.5289707Z`, not acquisition times.
Conditional register units are 3,762,883.24 modeled participants /
2,731,557.76 nonparticipants under unvalidated Civic-to-register exchangeability.
Register definitions, survey calibration, field period and population transport
remain unqualified. No observed staying home, group populations or design
interval is claimed.

Immutable release `438683276` has nine full byte-verified assets. The
98,816,162-byte / 16-member ZIP contains the complete 73,948,518-byte native
query archive, accepted version-09 baseline, every new query, maintained code,
unchanged Washington shared helpers and seven focused tests. 1,612 independent
parent/component/clock/Fraction/preservation/package checks and two blocked,
byte-identical offline reproductions pass. Maintained
`scripts/virginia_register_control.py` exports 51 state/D.C. rows, 26
source-control disposition records and fifteen conditional frames. The new
record is registration-only, **not an observed statewide ballot reference**.
All 50 unaffected states, fourteen prior frames and 25 prior controls survive.
No source acquisition, completed candidate/precinct/mode/geometry/private-survey
reduction or website campaign was repeated.

## Arizona registration-only parent and component conflicts

[Complete version-09 controls and sufficient native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-09/complete-analysis.zip)
reuse the held [native Arizona query](https://github.com/hanshanley/margin_of_error/releases/tag/voter-precinct-arizona-native-counts-20261105).
The API explicitly reports statewide `totalVoters=4,374,827`; all 15 locality
and registration totals agree. The native active/inactive components do not
explain those totals. Every component and its signed discrepancy is retained,
not used to repair the parent or invent an active/inactive definition.

The state `ballotsCast=0` conflicts with the county sum 2,248,900. The original
zero stays in the source query, while selected statewide ballots, turnout and
native-minus-model remain null. No county sum substitutes for state ballots.
All 15 county and 1,763 precinct inventory rows remain byte-identical.
Mohave's virtual `225_Non-Resident Property Owners` participation remains
missing, not zero. Native rate/map/completion holds remain unchanged.

The unofficial API's UTC clocks stay distinct: asOf
`2026-11-05T01:56:20.7372053Z`, lastUpdated `2026-11-05T01:56:17.3000739Z`
and publishDate `2026-11-05T03:50:35.7268964Z`; these are not acquisition times.
Conditional register units are 2,195,821.90 modeled participants /
2,179,005.10 nonparticipants under unvalidated Civic-to-register exchangeability.
Survey calibration, field period and population transport remain unqualified:
no observed staying home, demographic populations or design interval is claimed.

Immutable release `438672280` has ten full byte-verified assets. The
36,582,026-byte / 17-member ZIP contains the complete native query, accepted
version-08 baseline, every new query, maintained code, unchanged Washington
shared helpers and seven focused tests. 295 independent parent/component/
Fraction/preservation/package checks and two blocked, byte-identical offline
reproductions pass. Maintained `scripts/arizona_register_control.py` exports
51 state/D.C. rows, 25 source-control disposition records and fourteen
conditional frames. The new record is registration-only, **not an observed
statewide ballot reference**. All 50 unaffected states, thirteen prior frames
and 24 prior controls survive. No source acquisition, completed candidate/
precinct/private-survey reduction or website campaign was repeated.

## Washington registration-only parent frame

[Complete version-08 controls and sufficient native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-08/complete-analysis.zip)
reuse the already-held [39-county numerical snapshot](https://github.com/hanshanley/margin_of_error/releases/tag/voter-county-washington-participation-20261106-01).
The native state `totalVoters` parent explicitly supplies 5,170,951,
corroborated by county headers and the completed `voterRegistration` audit.
It is a source-defined registration frame, not an inferred county sum,
eligible population or independently validated survey population.

The state `ballotsCast=0` conflicts with the county sum 2,266,746. The original
zero stays in the source query, but selected statewide ballots, turnout and
native-minus-model are null. No county sum repairs the state result. All
39 county and 9,588 unit CSV rows remain byte-identical; King's 601,199 county
ballots stay unallocated despite its unit zeros. Native rate/map/completion
holds and absent state reporting status remain unchanged.

Native UTC clocks remain distinct: asOf `2026-11-05T04:01:31.3211464Z`,
lastUpdated `2026-11-05T03:57:41.6823065Z` and publishDate
`2026-11-05T04:07:12.8391684Z`. Active/inactive definition, survey calibration,
field period and population exchangeability remain unqualified. Conditional
units are 3,431,936.67 modeled participants / 1,739,014.33 nonparticipants,
not observed staying home or group populations; no design interval is supplied.
Both newer denied Washington routes remain stopped; no source is reacquired.

New immutable release `438661685` has nine full byte-verified assets. The
29,915,909-byte / 15-member ZIP includes the complete native query, accepted
version-07 baseline, every new query, maintained code and seven focused tests.
419 independent parent/Fraction/preservation/package checks and two blocked,
byte-identical offline reproductions pass. Maintained
`scripts/washington_register_control.py` exports 51 state/D.C. rows, 24
source-control disposition records and thirteen conditional frames. The new
record is registration-only, **not an observed statewide ballot reference**.
All 50 unaffected states, twelve prior frames and 23 prior controls survive.
Earlier native snapshot guarantees remain checksum/never-overwrite, not a
retroactive host-lock claim. No completed native-unit/private-survey reduction
or website campaign was repeated.

## Arkansas explicit parent registration frame

[Complete version-07 controls and sufficient native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-07/complete-analysis.zip)
reuse the held [native Arkansas query](https://github.com/hanshanley/margin_of_error/releases/tag/voter-precinct-arkansas-native-counts-20261105).
The explicit state parent has 1,856,404 registeredVoters and 893,026
totalBallotsCast / printed 48.11%. Both election/turnout API headers and all
75 county-parent sums agree. This is not a sum of partial leaf registrations.

The native snapshot is unofficial v173, lastUpdated
`2026-11-04T21:21:28.2891014Z`: 2,761 reporting and seven partial precincts,
not certified or completed counting. The full 2,768-row leaf query retains
1,108 missing registrations and 82 missing ballot totals byte-for-byte.
No missing values are filled or residuals allocated. Native rate/map holds,
including the earlier denied precinct asset and unqualified geometry, remain.

Conditional source-register units are 945,578.92 modeled participants /
910,825.08 nonparticipants; native-minus-model is separately -52,552.92.
Active/inactive register definition, survey calibration, field period and
population exchangeability remain unqualified. These are not observed
staying home, group populations or independent validation; generic cast-ballot
comparison fields remain blank and no design interval is supplied.

Immutable release `438650649` has nine full byte-verified assets. The
29,480,699-byte / 15-member ZIP includes the complete native query, accepted
version-06 baseline, every new query, maintained code and six focused tests.
579 independent parent/leaf/Fraction/preservation/package checks and two
blocked, byte-identical offline reproductions pass. Maintained
`scripts/arkansas_state_control.py` exports 51 state/D.C. rows, 23 controls
and twelve conditional frames, preserving all 50 unaffected states, eleven
prior frames and 22 prior controls. No completed candidate/private-survey
reduction, source acquisition or website campaign was repeated.

## Delaware held statewide registration frame

[Complete version-06 controls and sufficient native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-06/complete-analysis.zip)
integrate the already-published [native state/district query](https://github.com/hanshanley/margin_of_error/releases/tag/voter-state-delaware-native-participation-20261106-01),
not a new acquisition. The separate ALL row has 384,862 Ballots Cast /
810,407 Reg Voters / printed 47.49%; all 41 House-district sums reconcile.
Candidate selections, including the distinct 378,111 Senate total, remain
separate and are not participation counts.

Turnout clock, timezone and native FIPS are absent. The candidate clock and
client-generated cache key never fill that gap. Native rate/map/all-mode/
certification approvals remain false; no district counts are apportioned to
counties. This adds a conditional source-register frame, not approval of a
generic turnout rate or population match.

Conditional source units are 397,682.55 modeled participants / 412,724.45
nonparticipants under unvalidated Civic-to-register exchangeability. The
separate native-minus-model difference is -12,820.55 units, not observed
staying home or a cohort change. Native register status/timing, survey field
period, calibration and population transport remain unqualified; no design
interval is fabricated.

Immutable release `438634132` has eight complete byte-verified assets. The
21,218,192-byte / 14-member ZIP includes the complete native query, accepted
version-05 baseline, every new query, maintained code and six tests.
327 independent native-frame/Fraction/preservation/package checks and two
blocked, byte-identical offline reproductions pass. Existing native candidate
and private survey reductions are reused, not repeated. Maintained
`scripts/delaware_registration_control.py` exports 51 state/D.C. rows, 22
controls and eleven conditional frames, preserving the 50 unaffected states,
ten prior frames and 21 prior controls. No new website view is claimed.

## New Mexico source-defined 2026 participation

[Complete version-05 state controls and native originals](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-05/complete-analysis.zip)
add a previously absent state reference: all 33 counties and 2,204 native
precincts reconcile to 731,209 native participants / 1,469,718 registered voters,
printed 49.75%. The [ordinary official export](https://electionresults.sos.nm.gov/VoterTurnoutDetails.aspx?map=TURN) explicitly labels Registered
Voters and Votes Cast; the webpage says Ballots Cast, and its general-election
definition refers to voters signing in. Those literal meanings are retained,
not silently promoted to the generic cast-ballot field.

The source is unofficial, updated November 6, 2026 at 9:55 AM MT. Full precinct
reporting is not certification or completed counting. The download's literal
November 8 clock has no declared timezone. Sandoval PCT051 retains zero
registration and printed 0.00%, but its analytic rate is null. Geometry and
demographic survey allocation remain unapproved.

The new conditional register frame supplies 765,694.90 modeled participant
units and 704,023.10 nonparticipant units, assuming unvalidated Civic-to-register
exchangeability. Native-minus-model is separately -34,485.90 units. These are
not observed staying home or independent population validation. The separate
October 30 registration report totals 1,462,993; its 6,725 difference remains
a dated source comparison, not a repaired denominator or cohort movement.
Party columns describe registration accounting, not voting behavior.

Immutable release `438620865` has twelve complete byte-verified assets.
The 21,147,874-byte / 22-member ZIP includes all sufficient originals, complete
baseline, code, six tests and dependencies. Independent verification passed
9,018 checks, including every native precinct counter in HTML and XLSX, exact
fractions, preserved outputs and two blocked byte-identical offline reproductions.
Maintained `scripts/new_mexico_participation.py` exports all 51 state/D.C. rows,
21 controls and ten conditional frames, preserving the 50 unaffected states
and nine prior scenarios. No original private respondent reduction, new website
view, group-rate fabrication or source-count calibration.

## California official 2026 registration reference

[Complete originals, native queries and preserved all-state results](https://github.com/hanshanley/margin_of_error/releases/download/participation-california-register-frame-20261108-01/complete-analysis.zip)
qualify the October 19, 2026 Report of Registration. All 58 counties and separate
state totals reconcile across county, six native age bins and preregistration
tables. The 23,273,590 registrations corroborate the existing CA denominator;
all 51 prior state rows and nine scenarios remain byte-identical. No duplicate
scenario or changed estimate. Equal counts do not prove results-system lineage,
matching survey populations or transport.

The separate 124,180 preregistrations overlap active registrations; they are
never added or subtracted as a disjoint population. The youngest native age bin
is `17.5* - 25`, including activated 17-year-olds for an upcoming election.
Civic bins are incompatible and never split. The printed eligible-population
estimate is unofficial, not registration. Party columns remain registration
accounting, not candidate behavior or demographic turnout.

Immutable release `438609932` has ten full byte-verified assets. The
59,145,983-byte / 24-member ZIP includes all eight originals and the complete
permitted baseline. Six tests, 2,256 independent checks (all 1,652 PDF count
cells), all 2,901 native workbook cells and two blocked, byte-identical offline
reproductions pass. Maintained `scripts/california_registration.py` reproduces
the complete query. This is source evidence, not a new website view.

**Georgia follow-up access hold, November 8, 2026:** a newer official results
API retrieval returned HTTP403; distinct official registration-hub and active
report pages also returned403 on direct retrieval. All three routes are stopped,
without another client, cache or mirror. The saved159-county ballot query and
two missing registration fields remain unchanged. Do not adopt modeled
third-party registration totals or infer the missing county values.

## Every-state historical demographic participation

[Complete results and reproducible inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-cps-state-demographics-20261108-01/complete-analysis.zip):
all 50 states plus D.C., 2022 midterm and 2024 presidential frames, with
1,734 state/year/group rows. The 1,733 positive-source estimates aggregate
already-held public CPS joint cells directly. Idaho's 2022 Black non-Hispanic
group has no source cell, not zero participation. Age, sex, education and the
exclusive race/Hispanic-origin partition retain native categories.

The denominator is all source-weighted civilian noninstitutionalized adult
citizens, including every unknown/noninterview class. Known-response-only rates
are separate. The 256 raw-n-under-30 flags are small-sample diagnostics, not
precision guarantees. The 5,202 unknown-assignment scenarios are not confidence
intervals or actual-turnout bounds. No legal-eligibility/register fabrication,
2026 forecast, observed staying-home or county/precinct allocation is supplied.

Maintained `scripts/cps_state_groups.py` and six tests reproduce every query.
All 11,906 source decisions, 6,120 partitions and 102 native state comparisons
are included; state overall rates differ by less than 0.05 percentage points
without adjustment. This audits input handling, not independent validation.
The immutable release `438552376` has seven full byte-verified assets;
26,243,365-byte ZIP SHA-256
`4e5bb73ce17229474eb3f2a549ddb0dced20a4569dd6b13e8fbbb11677788756`.
Independent verification passed 582,345 checks and two exact blocked-network/
external-execution reproductions. Both complete input bundles include their
originals/provenance.

The existing Demographics tab is now live at website revision `ca883d0`,
Pages `42530121113`, artifact `13637596097`. All 30 production browser
configurations pass, including every 1,734 state/group value on desktop/mobile,
102 no-JavaScript overall rows, source failures, tab/URL state and the preserved
AP/Civic views. Choose 2022 or 2024, then Geography. Missing Idaho stays absent;
sparse rates are descriptive, not precise or design-qualified. The 106-word
Methods overview, all 3,119 previous links, 265 IDs, 436 complete routes, native
preview and old source pin remain. Downloaded native content is 981,301,627
bytes / tar 983,808,000 bytes; both strict limits pass. Governing receipt:
`all-state-demographics-production-acceptance-01.json`. This completes the
historical all-state increment, not nationwide 2026 demographic/precinct coverage.

## Florida statewide registration-frame comparison

The [complete version-04 control package](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-04/complete-analysis.zip)
adds the already-held immutable Florida numerical source to the complete
51-state/D.C. query. All 50 unaffected state rows, 19 prior controls and eight
prior scenarios remain identical. There are now 20 native observations,
14 selected references and nine conditional statewide registration frames.

Florida's separate native TOTAL reconciles all 67 counties and 680 cells:
8,335,497 reported participants / 13,704,495 eligible active registrations,
native 60.82%. The register is the source October 5 deadline/report-generation
frame; native update time/timezone and statewide completion flags remain null.
Sixty counties retain unfinished provisional and 64 unfinished overseas flags.
Native Voter Turnout remains reported participants, not an automatically
qualified generic cast-ballot counter. Original generic/map approval stays false.

Existing Civic weights (4,180 Florida cases; 54.5488788613% modeled share)
give **7,475,648.38 conditional modeled participant register units** and
**6,228,846.62 modeled nonparticipant units**. Native-minus-model is
859,848.62, separately labeled. Exchangeability to this register is unvalidated;
these are not observed staying home, demographic populations, independent
population validation or county/precinct allocations. No source reweighting,
outcome fit or confidence interval is applied.

Immutable release `438515810`, tag `participation-state-controls-20261108-04`,
has nine complete assets verified against full authenticated draft and anonymous
published bytes. ZIP 20,157,249 bytes / 23 members, SHA-256
`99bad46c6c8142c8a92dd0a60f1863929b9ecaf930b290a0aec9fd3f3d3ae101`.
All sufficient permitted inputs, native numerical source, complete queries,
code and 21 tests are included. Independent verification passed 4,165 checks;
two network/external-execution-blocked reproductions byte-match every member
and the full ZIP. Receipts: `florida-state-controls-immutable-release-01.json`
and `florida-state-controls-independent-verification-01.json`.
The recorded DOS generic turnout-index 403 remains stopped; no new acquisition,
private records, acquisition headers or compiled publisher app code.
This is a research download, not a new website view; accepted `96d7257` remains.

## Website Methods and GitHub documentation

The website's Methods tab is now a **106-word estimation overview**, not a
source inventory. It explains weighted rates, matching denominators, historical
checks and supported geography, with a direct link to `METHODOLOGY.md`.
Legacy detailed anchors remain accessible, but normal Methods navigation hides
the archive. GitHub now separates the concise README and current methods from
the data catalog, reproduction guide, indexed source ledger, dated package
notes and original research protocol. Initial documentation revision `4546524`
preserves all previous complete-download links.

Accepted website revision `96d725787aeaab4ac611a2eecaf47f212a16b57e`, Pages
`42517487539`, deployed artifact `13632291877`: the downloaded ZIP hash and
streamed native tar verify actual content **981,248,921 bytes** and tar
**983,756,800 bytes**. All 24 production browser modes pass, including desktop,
mobile, no-JavaScript, legacy links, source failures and every AP public row.
All 3,107 prior links, 263 IDs, 436 complete relocations, pinned data and the
original preview remain. Both credential workflows pass; old dirty local HEADs,
real indices and unrelated files are preserved. No estimates, source data or
release assets changed. Governing receipts:
`methods-overview-production-acceptance-01.json`,
`methods-overview-native-pages-artifact-proof-01.json` and
`methods-research-docs-push-01.json`. This increment is complete; broader research
remains open under the existing single 15-minute continuation.

## Historical CPS group registration and response frames

### Native state voting/registration pairs and AP diagnostics

Maintained `scripts/cps_state_frames.py` now uses the already-held native
`a5a.xlsx` / `a5b.xlsx` presidential voting/registration tables for 1972-2024
and `hst_vote03a.xlsx` / `hst_vote03b.xlsx` congressional tables for 1974-2022.
These are complementary election types, not old/new copies. All original
bytes, titles, cells, population headers, source rows, notes and acquisition
clocks remain included. The entire existing 2,503-row public voting query is
preserved and independently bound to the original cells, not recomputed or
replaced by a new vintage.

The complete state query contains 5,202 native percentage cells and 2,754
state/year/population pairs for every state plus D.C. There are 2,503
supported native marginal ratios, 153 absent early citizen columns and
2,550 same-election-type comparisons. Original unavailable `N` cells are
not zero: 1972/1974 report only the largest 15 states, 1976 only the largest
25. Citizen measurement before 1996 remains explicitly cautioned; crossing
that definition boundary is held rather than harmonized.

All 768 supported AP state-weight comparisons keep poll-close/final frames,
the full source weight and unknown mass separate. All 1,204 query/population
decisions, including national/demographic/support/unavailability holds, are
included. CPS vote/register ratios of self-reported percentages are not an
individual registered-voter joint or administrative turnout. These are
source-specific diagnostics, not independent validation, population
transport, retention/switching or observed staying home. No percent is
multiplied by VEP/CVAP to fabricate a registration total; no local or
demographic allocation is performed.

The [complete immutable state-frame release](https://github.com/hanshanley/margin_of_error/releases/tag/participation-cps-state-frames-20261108-01)
is `438432114`, with nine full assets verified against authenticated draft
and anonymous published bytes. The complete ZIP is 368,608 bytes / 19
members, SHA-256
`bda083bac82cd4ac43a7f50e99a02a1c0d15113da9cb0341e9e5a1908a77152e`.
It includes all originals, sufficient caches/metadata, preserved voting
observations, selected public aggregates, every query, code and tests.
Seven focused tests, 80,133 independent original-cell/full-query/member
checks and two network/external-command-blocked byte-identical reproductions
passed under seeds 3 and 97. Session proofs:
`cps-state-frames-immutable-release-01.json`,
`cps-state-frames-independent-verification-01.json` and
`cps-state-frames-offline-reproduction-01-A.json` / `-B.json`.
This is a research publication, not a new website view or deployment.

Maintained `scripts/cps_group_frames.py` now uses all 26 already-held native
election tables 1/5 for 2000-2024 plus the two full historical workbooks
`hst_vote01.xlsx` and `hst_vote02.xlsx`. Their original bytes, source clocks,
all worksheet cells, headers, notes and margins remain included. No new source
requests were made. Estimate sheets are selected by their native contents,
not the workbook's active tab: some 2016-2020 files open on margins-of-error
sheets. Table 5's inline margins sections are also explicitly held.

The native 2006/2008 citizen headers still use merged `Not Registered` /
`Did Not Vote` classes. The 2010-2014 `Reported did not vote` label is a
different header variant with separately reported nonresponse. All literal
counts and their population scopes are retained, not repaired. The legacy
citizen population is a declared sum only where its two native citizen
registration components supply it; citizen registration is not confused
with total-resident nonregistration. Published weighted thousand-person
counts are not administrative voter/register totals.

| Complete query | Actual rows |
|---|---|
| Native age/sex/education group counts, 2000-2024 | 3,203 |
| Historical registration/voting percentage frames, 1964-2024 | 2,573 across all 31 elections; native `N` and absent registration years remain |
| Original election-workbook row decisions | 4,540, including every held margin/header/note row |
| Separate native voting-nonresponse assignments | 3,792, never a split of old merged unknown classes |
| Same presidential/midterm-type snapshot comparisons | 2,407, preserving age/race/citizenship/education breaks |
| Public AP source/frame decisions | All 602, without unqualified national population scaling |

The historical series also preserves region/labor-force/education percentages
and race/ethnicity/sex by native age groups. Overlapping parent, child and
demographic groups are not added or multiplied. Source voting/registration
marginal ratios do not identify individual registered-voter participation.
Unknown-response assignments vary only the explicit native unknown count,
using the full citizen denominator; they neither correct self-report error
nor bound actual administrative turnout. No confidence interval, observed
staying home, retention/switching, new eligibility or local allocation is
inferred. AP `US50_SOURCE`, native demographic meanings and CPS U.S. resident
population frames remain unmatched for population scaling; gender is not
silently recoded to native CPS sex.

The [complete immutable CPS release](https://github.com/hanshanley/margin_of_error/releases/tag/participation-cps-group-frames-20261108-01)
is `438418451`, with all ten full assets independently compared before and
after publication. Its complete ZIP is 1,289,064 bytes / 43 members, SHA-256
`1655df1430d09c5206f6ad1f7e582277f02b81cf43be135b6508bd7e142485fb`.
All 28 government originals, full sufficient caches/metadata/selected public
aggregate inputs, all queries, code and tests are included. There are no
raw survey microdata, voter identifiers or private fine cells.
Nine focused tests, 221,990 independent original-cell/full-query/member
checks and two blocked-network/external-command byte-identical reproductions
passed under seeds 3 and 97. Governing session receipts:
`cps-group-frames-immutable-release-01.json`,
`cps-group-frames-independent-verification-01.json` and
`cps-group-frames-offline-reproduction-01-A.json` / `-B.json`.
No new website view or deployment is claimed.

## Held EAC historical state controls: complete verified publication

Maintained `scripts/eac_state_controls.py` now uses the already-held November 4
EAVS archive and complete 67,525-row local query. No new request was made to
later-denied EAC routes. Thirteen 2008-2024 F1 selections retain their exact
native source dictionaries, sheets, row numbers, hashes and retrieval clocks;
the two earlier Alaska observations remain unqualified inventory.
Eleven registration rows are joined by exact state, ID and jurisdiction name
against native A tables, including the separately held 2010/2012 workbooks.
Their values match the frozen local query; neither count equality nor a
statewide label substitutes for geographic or denominator qualification.
Native instrument labels are independently checked against included worksheet
cells. Original filenames, including the XLS-labeled 2010 XLSX bytes, are retained.

| Full output | Rows / disposition |
|---|---|
| Complete state/year grid, 2004-2024 | 561, including every missing state/year |
| Complete native or held observation ledger | 15; ten selected source references, nine qualified source-defined participation references |
| Separate AP/register scenarios | Six Alaska frames: 2020, 2022 and 2024 final/poll-close; no absent 2018 state row invented |
| Complete public survey-query decisions | All 602 supplied selected public aggregates, including every unmatched/support/frame disposition |
| Adjacent native snapshot comparisons | Ten; seven source-defined, unharmonized differences and three held endpoint comparisons |

Alaska's 2018/2020/2022/2024 A1 total equals active plus inactive records.
These are particular native registration frames, not eligible/citizen
population denominators. The 2024 native `f2_4=1` marks a highest-office
participation proxy: its rate and conditional-minus-native diagnostic stay
null. Maine's 2014 total 776 is explicitly UOCAVA-only. NH/RI 2008 source
labels do not establish whole-electorate scope. All native zeros, unavailable
flags, source comments and unknown mass remain; early time-series rows do not
inherit modern qualification. No count is silently relabeled ballots cast.

`R*p`, `R*(1-p)` and any unknown mass retain the full source denominator.
Exchangeability to the native total register is unvalidated. AP final/poll-close
weights remain separate views of the same sample and may already calibrate
outcomes; conditional differences are not independent validation. Native
question meanings and adjacent presidential/midterm electorates are not
harmonized. No demographic/local allocation, administrative staying home,
individual retention or eligibility/death/migration counts are inferred.

The [complete immutable release](https://github.com/hanshanley/margin_of_error/releases/tag/participation-eac-state-controls-20261108-01)
is release `438401507`, with all nine full assets. Its 21-member ZIP is
192,220,123 bytes, SHA-256
`2575491662c9909f77ca18ac88e7bfd620b75b490024155b83758b0684d0f6ee`.
It includes the complete 44,477,301-byte government source archive,
3,922,371-byte full local query, 135,971,213-byte earlier time-series original,
supplemental registration originals, guide/instruments, source-bound caches,
all sufficient selected public survey inputs, all queries, code and tests.
It is not a metadata-only download and contains no raw survey respondents
or voter identifiers. The earlier original remains included but unqualified.

Ten focused tests and 11,326 independent native-cell, definition, source,
full-query and archive-member checks passed. Two standard-library
reproductions with network and external-process execution blocked match
every member and the entire ZIP under seeds 3 and 97. All nine assets match
their authenticated draft and anonymous published full bytes.
Governing session proofs: `eac-state-controls-immutable-release-01.json`,
`eac-state-controls-independent-verification-01.json` and
`eac-state-controls-offline-reproduction-01-A.json` / `-B.json`.
No new website view or deployment is claimed by this research release.

## Website repair: source-backed navigation and precinct coverage

The user-reported empty state selection, inconsistent tab defaults,
North Carolina-only Precincts selector and unstructured Methods area are fixed
in live website revision `5e11695ed8d5e81cf1634a737829ec8c6cd9a287`.
The repair preserves the intervening automatic county refreshes; it does not
replace those snapshots or change the pinned participation research source.
Each tab retains supported state/year/group/measure choices, and precinct
choices are derived from the actual loaded coverage. NC's specialized
historical controls remain. Where county/precinct participation is unavailable,
available candidate counts are shown with a separate explicit results-color
control; they are never relabeled turnout. Methods now groups definitions,
2026 sources, research and complete-data access.

Actual Pages run `42502356194`, attempt 1, deployed fresh artifact
`13625184708`: uploaded/deployed IDs match, actual payload 981,247,039 bytes,
tar 983,756,800 bytes, with 16,243,200 bytes of strict tar headroom.
Artifact digest:
`sha256:17a62519f30c9296a36756c6a415ddc721d2609f02b2eb836898dd763a7c541b`.
Main/review credential runs `42502356263` / `42502253300` passed.
HTML SHA-256:
`b4c17fe8e0850ffd1a898de6df26c1224047281c9d62ca883161284ba96b48ce`.
Actual served HTML, CSS, scripts, source pointers and relocation manifest
match the reviewed build. All 3,103 prior link occurrences and 260 IDs remain;
the revised page has 3,107 links and 263 IDs, with no additional script URLs.
The native preview remains byte-identical to the previous deployment.

Seven tab/source-failure/deep-link/no-JavaScript configurations, three
county-fallback configurations, 14 existing landing/AP/Civic modes, two
51-state turnout-navigation modes and 62 outline checks passed on production.
Independent drawn-value checks match every key, contest count and margin
for 9,718 Texas 2024 precinct shapes, and every ballot, registration and rate
for 4,105 Minnesota 2026 rows. Minnesota's 2,370 observed and 1,735 held or
unavailable rates remain distinct; partial reporting is not completed turnout.
Every one of the 602 public AP rows still passes the source-matched view checks.

The only new data relocation covers four complete November 4 archived
nationwide snapshots at the unchanged pinned source revision `792e3d`.
All 16,260,811 bytes were individually verified against their originals,
including browser-origin CORS and JSON parsing, before removing only redundant
build copies. All 432 previous full-file receipts are unchanged; the manifest
now contains 436 complete relocations. No original input, current snapshot,
complete archive or source frame was reduced. The standalone compatibility
renderer uses the same routing, and its export retains every original data byte.
Local/native gzip differences were verified as OS-header byte 9 only; decoded
data and all other compressed bytes agree.

Governing active-session proof: `website-repair-production-acceptance-01.json`;
native source-value proof: `participation-precinct-source-values-production-01.json`.
The broader historical/group denominator and source-coverage work below
remains open. This completed UI repair is not completion of the research project.

## Wyoming declared registration reports and source-weighted scenarios

Both newly acquired primary PDFs returned HTTP 200 on November 8, 2026,
at 05:23 UTC:

| Native report | Held bytes / SHA-256 | Scope |
|---|---|---|
| [November 3, 2026 register](https://sos.wyo.gov/Elections/Docs/VRStats/2026/26Nov3_GeneralElection_VR_Stats.pdf) | 106,133 / `1efb8228fa33e7a34c8b0754e5720f2fcad3e9e63869f28adfe579757e2c2d40` | One general-election-labeled snapshot, 23 counties and a separately declared state total of 281,219. |
| [2022 annual report](https://sos.wyo.gov/Elections/Docs/VRStats/2022VR_stats.pdf) | 381,890 / `de446008b82813cfdd1427c8a03a7164a702683183ed5bebb4b0c0a88a4ed3ca` | Fourteen dated pages: 12 monthly, August 16 primary and November 8 general; the last reports 297,639. |

Both PDF engines independently select the same 360 county/state records.
Every row's six literal registration-party categories sum to its native total,
and all 105 county-to-state column checks reconcile. Parents are never added
to children. Native `Other*` and its former-party footnote remain source
accounting, not a vote-choice alias or party-specific participation estimate.
The general-election tables were also reviewed as rendered originals.
Nonbreaking spaces in two monthly county labels are whitespace, not new units.

Neither PDF declares active/inactive scope or inclusion of Election Day
registrants. The 2022 general count equals the separate profile's explicitly
day-before register, but equality is not independent validation or proof of a
final electorate frame. The 2026 native HTTP Last-Modified is November 3 at
13:36:20 UTC; this is a transport timestamp, not an asserted native count
cutoff. Existing election-time registration denominators remain null.
Ballot/register snapshot ratios are labeled arithmetic context, not
registered-voter turnout. The -16,420 state registration-snapshot difference
does not identify original-cohort loss, eligibility, deaths or migration.

Maintained `scripts/wyoming_registration_controls.py` joins only whole-state
overall published aggregates to their same-year general-registration snapshot.
It preserves AP 2022 `FINALVOTE_STATE_WEIGHT` and `POLLCLOSE_STATE_WEIGHT`
as two different frames, plus Civic 2026. Civic's modeled share
0.693917633232253022 yields conditional counts 195,142.82 / 86,076.18
on the native 281,219 register. Exchangeability to that exact snapshot is
unvalidated; model nonvoter is not administratively observed staying home.
All model mass, including unknowns, stays in the denominator. No county or
precinct gets a state survey propensity, no cross-study model-count change
or false confidence interval is inferred, and final weights may already use
election outcomes. The positive-case support screen for AP and source-case
screen for Civic are not a precision or privacy guarantee.

The [complete immutable analysis](https://github.com/hanshanley/margin_of_error/releases/download/participation-wyoming-registration-20261108-01/complete-analysis.zip)
is release `438053365`: 642,261 bytes, 20 members, SHA-256
`0c1181e6106516c8b37eda7a10d0b2861a6c478d2de816280fa38d34dce1f273`.
All eight full assets were authenticated-draft and anonymous-published
byte-verified. It includes all originals used, both source-bound text
selections, full unchanged public reference/survey inputs, all 360 native
rows, 105 accounting rows, 24 snapshot changes, two source comparisons,
three conditional rows and 681 public-aggregate dispositions, code and tests.
Seven focused tests and 4,885 independent native/Fraction/source/archive
checks passed. Both network/external-command-blocked reproductions matched
every member and the complete ZIP. Prior inputs, weights, scenarios, source
selections, registration nulls and immutable releases remain unchanged.
Governing active-session receipts: `wyoming-registration-controls-verification-01.json`
and `wyoming-registration-controls-immutable-release-01.json`.
The [three-frame folded view](https://www.themarginoferror.com/voter-participation/#participation-wyoming-registration)
is now live in website revision `37f2c47bab5b915f18edde2075053d2679ed6b61`,
actual Pages run `42451862788`, attempt 1, fresh artifact `13605868963`.
Uploaded and deployed artifact IDs match; actual payload is 997,476,489 bytes,
tar 999,987,200 bytes, with 12,800 bytes of strict tar headroom.
Artifact digest:
`sha256:6d9c1fc96553d2ecbe1ab893052ac2a98099fc7dddb5bb6ea5876b03a4e0c221`.
All 24 production modes passed: the three new source-matched scenarios,
seven native observations, every 602-row AP selection and existing Civic/
landing/failure behavior. Four direct-link configurations also pass on desktop
and mobile, with and without JavaScript. All 3,073 old links, 258 IDs and
previous complete assets remain; eight new links bring complete downloads
to 1,078. Only HTML changed (+5,321 bytes), SHA-256
`38e0fc04c041596ce021b55b750f573ee1a958d5690e4800e78ae4583ddd70ef`.
All other prepared bytes and served scripts/source pointers match; no client
script, stylesheet or homepage card was added. Main/review credential runs
`42451862725` / `42451774078` passed. Governing active-session receipt:
`wyoming-registration-production-acceptance-01.json`.

## Wyoming official historical statistics and registration-frame qualification

The distinct primary [voter registration and turnout table](https://sos.wyo.gov/Elections/Docs/VoterProfile.pdf)
and [declared registration index](https://sos.wyo.gov/Elections/VRStats.aspx)
were acquired directly with HTTP 200 on November 8, 2026, at 05:09 UTC.
The actual 101,792-byte PDF is revised **08/2026**, SHA-256
`aea5863d565d3f6831e56ee9c6fe9f3d439e625cb8a681bcd5d201ebf2170568`;
the older search-index text is not the acquired source version.
All 25 even years, 1978-2026, are retained separately for primary and general
elections. The 2026 general cells are blank; the populated 2026 fields concern
the primary election. The native PDF and two independent text extractions
agree, and the original rendered table was reviewed.

The registration footnote excludes Election Day registrations: these are
day-before counts, not a qualified election-time registered-voter denominator.
Seven general-election turnout counts exceed the corresponding pre-election
register; this does not establish a registered-turnout rate or a count of
Election Day registrants. Native voting-age population is estimated VAP,
not citizen VAP or eligible voters. Native `Voter Turnout` remains distinct
from separately qualified cast-ballot observations. The 2022 general count
198,198 agrees with the primary statewide ballot summary, but is not
independent validation. No existing registration null or held aggregate changes.

The source prints 54% for 2024 primary registration despite its counts
226,062 / 454,508 implying approximately 49.7%. Both values remain in the
complete query with `source_disagreement`; no native correction is made.
All other printed registration/turnout percentages pass their stated display
precision. Blank 2026 general cells remain unknown rather than zero.

Maintained `scripts/wyoming_participation_statistics.py` produces 50 complete
primary/general rows, 50 matched/unmatched selected-control comparisons and
48 same-election-type changes. The
[complete immutable analysis](https://github.com/hanshanley/margin_of_error/releases/download/participation-wyoming-statistics-20261108-01/complete-analysis.zip)
is release `438048192`, 114,978 bytes, 13 members, SHA-256
`e670e9d2e781d34e734156fb2a2c60223c06dcddd30ba686a63f59b7670ce91a`.
All five full assets were authenticated-draft and anonymous-published
byte-verified. Seven focused tests, 1,220 independent native/Fraction/source/
archive checks and two network/external-command-blocked reproductions passed;
every member and the complete ZIP match exactly. It includes the native
aggregate PDF, both source-bound text extractions, sanitized receipt, complete
255-row reference input, all queries, code and tests. Existing modeled shares,
conditional scenarios and historical source selections are unchanged.
This is a research download; no new website view is claimed.
Governing active-session receipts: `wyoming-statistics-verification-01.json`
and `wyoming-statistics-immutable-release-01.json`.

The index's November 3, 2026 registration PDF and 2022 annual report have now
been acquired and qualified as distinct registration snapshots, as recorded
above. Neither that increment nor the historical table resolves final
registration or precinct denominators.

## Historical administrative participation comparison

Maintained `scripts/historical_participation_controls.py` now joins the approved
public AP/Civic aggregates to source-specific state-year controls without
reconstructing private respondents. The
[complete immutable historical analysis](https://github.com/hanshanley/margin_of_error/releases/download/participation-historical-controls-20261108-02/complete-analysis.zip)
is release `438041499`: 4,976,404 bytes, 18 ZIP members, SHA-256
`e2cc5cfdf19220a20204405fd10329f2f38bb1c3822c06667e3b1513c53407c0`.
All seven complete assets were authenticated-draft and anonymous-published
byte-verified. It retains all 255 state/D.C.-year combinations, 434 separate
survey/weight rows, 18 source references, 16 conditional registration-frame
rows, 11 administrative comparisons and 18 literal native mode rows.
Fifteen selected references qualify as cast-ballot measures; three retain other
native meanings. A separate complete 25-observation source ledger retains the
unselected, held Wyoming unit aggregate alongside the direct state source.

The already-held Hawaii original archive supplies historical statewide
`histatewide.pdf` and `summary.txt`, not reused 2026 layouts:

| Year | Native total turnout | Native total registration | Native print clock |
|---|---:|---:|---|
| 2018 | 398,657 | 756,751 | November 15, 2018, 5:13:49 p.m. |
| 2020 | 579,784 | 832,466 | November 19, 2020, 10:21:05 a.m. |
| 2022 | 419,363 | 861,358 | November 22, 2022, 12:39:46 p.m. |
| 2024 | 522,236 | 860,868 | November 13, 2024, 6:51:06 p.m. |

These are source-labeled final reports, not independently certified outcomes.
Native UTF-8/UTF-16 encodings, quoted multiline records, omitted trailing
header fields and repeated registration values are handled explicitly.
PDF turnout modes independently sum to the same statewide totals, while
legacy CSV/PDF mode labels remain separate and unharmonized. Hawaii 2022
`Counted Precincts=0` is preserved, not interpreted as zero ballots.
No raw voter/survey records, acquisition session headers or compiled publisher
app code is included. Source-bound PDF text and all sufficient original
aggregate files are included for package-only offline reproduction.

The native Wyoming 2022 unit review has 439 units in 23 counties, and its
original aggregate approval remains **withheld**: Natrona's precinct and statewide values
are 22,955, while its printed county total is 22,957. The 198,198 workbook sum
remains a held native measure. Version 02 separately selects the primary
statewide ballot summary described below, not that held aggregate. Its
-6,510 difference to the 2026 source is a reported state snapshot difference,
not final-count turnout decline. Both Wyoming registration denominators remain
null, and changing precinct sets are not linked by reused labels.

Eight focused historical tests, 24 combined historical/current tests and 4,570
independent Fraction/source/scope/preservation/archive checks passed.
A second PDF engine independently verified all four Hawaii historical totals.
Both blocked-network/DNS/external-command reproductions matched every member
and the complete ZIP; all 50 current Civic shares and eight current scenarios
remain unchanged. AP poll-close/final weights remain separate and may already
reflect outcome calibration. No source-model independence, AP/Civic construct
harmonization, fixed-cohort participation, demographic allocation, causal
decomposition or confidence interval is inferred. Eligibility/death/migration
remain unknown.

The separate Wyoming statewide source-selection update was accepted in website revision
`24b89a991f149714068e54fbb91048ae1d2d5e02`, actual Pages run `42449476639`,
attempt 1, fresh artifact `13604789540`. The uploaded/deployed artifact identity
matches; its actual payload is 997,471,168 bytes and tar 999,987,200 bytes,
both strictly below 1 GB, with 12,800 bytes of tar headroom.
Artifact digest:
`sha256:8e34522c529779225b6232557bc4864f7344e362e58406a6f9c2695887a33d52`.
All 19 production modes passed, including all seven source-matched
administrative rows, every 602-row AP selection and existing Civic/folded-
research behavior. All 3,066 prior links, 258 IDs and six first-version assets
remain; the seven new full assets bring complete download links to 1,070.
Only the intended HTML changed, by 2,155 bytes; no client script was added,
and served scripts/source pointers match the exact build.
HTML SHA-256:
`0c602438c2f4fb111c7a416bb0fa5c6e4f303e45e959b415054a809787de087f`.
Main/review credential runs `42449476675` / `42449392752` passed.
Governing receipt: active-session
`historical-controls-production-acceptance-02.json`; first-version acceptance
`historical-controls-production-acceptance-01.json` remains preserved.

**Separate Wyoming primary source, selected in version 02:**
the held `2022_General_Statewide_Total_Ballots_Cast_Summary.pdf` and
`2022_General_Summaries_Results.xlsx` both explicitly report 198,198 statewide
ballots and 22,955 for Natrona. All 23 county rows match the native precinct
sums; both constitutional-amendment notes independently state 198,198 and a
99,100-vote majority. PDF SHA-256:
`51ad76bbc0baa0851c008ca42eca7f7eb40e3c4cab6e983f38889544d1807b2d`;
native summary workbook SHA-256:
`230ee0bcf9a2d9d3a9373dfba7e771d74e1daa9a22f4eec81e5e26181a5c25a4`.
Version 02 uses a separately identified primary statewide ballot reference,
without changing the original held unit-aggregate approval, the conflicting
22,957 county print, registration unknowns or geography/rate holds. The new
version retains both observations and explicit source selection rather
than mutating the immutable first package. Qualification receipt:
`wyoming-2022-direct-statewide-reference-qualification-01.json`.

The new source-selection increment passed ten historical/26 combined tests,
1,973 independent preservation/source-selection/archive checks, and two
blocked-network/DNS/external-command reproductions matching all 18 members
and the full ZIP. All 254 unaffected state/year rows, 432 unaffected survey
rows, all modeled shares and 16 conditional scenarios, the other ten time
comparisons, all 18 mode rows and all six previous inputs remain unchanged.
The original held aggregate and printed 22,957 county figure are preserved.
The immutable first release and its earlier verification remain available.
The version-02 website source-selection update is live and exact-production
verified as described above; all first-version complete downloads remain
available. Its distinct state-level qualification does not resolve the held
county/precinct approval, registration or boundary questions.

## Reusing already-held EAC originals for the next historical controls

The existing November 4 acquisition predates the later denied native URL
requests recorded below. Its saved `participation-methods/20261104T183000Z`
source index and complete original-source archive hold the 2008-2024 EAVS
inputs, including the 2018 CSV and 2020/2022/2024 ZIPs. The separate
`participation-local/20261104T220000Z` export has 67,525 complete local
observations and exact-identity registration joins. **Do not reacquire those
files or retry the later denied URLs.** Their possession is not new proof
of statewide completeness or source/model independence.

The already-held jurisdiction time-series workbook is 135,971,213 bytes,
SHA-256 `3fec2bbcb03fd32148d7213e04a6bdfc3ff38b0b83236824d4a5c7945451b169`,
with the official guide also held. Its large workbook inspection is complete;
reuse `eac-held-native-inspection-01.txt` / `eac-held-native-discovery-01.json`
in the active session rather than repeating it. The exploratory zero-padding
filter also accepts missing IDs: its count of 527 is **not qualified
statewide coverage**. Use original IDs and native scope, not padded zeros.

The existing local export has only 15 statewide-unit flags: Alaska's eleven
2004-2024 rows, D.C. 2008, New Hampshire/Rhode Island 2008 and Maine 2014.
Critically, Maine's state-labeled 776 count explicitly covers **UOCAVA only**;
it must remain visible and held, never promoted to whole-state turnout.
The guide also warns that the separate county-collapsed product divides
cross-county jurisdiction counts equally. That product is not a native
county panel and is not the jurisdiction-level input selected here.
Counted-ballot, participation, registration and source-year definitions
remain separate. No state survey propensity is allocated to local units.

Next qualify the native rows, scope and denominator definitions against their
bound originals, then produce complete matched/unmatched historical state-year
queries and supported whole-state survey-frame scenarios. No new EAC
statewide control, aggregation or conditional estimate is certified by this
discovery alone.

## Status and source classes

| Class | Meaning |
|---|---|
| Primary administrative | Election office or other government producer of the records. |
| Primary survey | Producer of the survey and its public-use documentation. |
| Official compilation | Government aggregation of jurisdiction-reported figures. |
| Academic compilation | Harmonized returns collected from primary election offices. |
| Secondary compilation | Repackaged feeds, derived comparisons, or analysis. |
| Method/reference | Definitions, access rules, geography, or methodological evidence. |

`held` means native bytes or a qualified factual selection is saved. `reviewed`
means the stated checks passed, not that every geography or inference is valid.
`lead` means identified but not acquired/qualified. `request` means a procedural
route, not data absence. `blocked route` refers only to the observed URL/access
attempt; it is not a claim that the publisher's data are unavailable everywhere.

## Primary administrative data and population denominators

| ID | Publisher / entry point | Data and scope | Holdings / automation location | Required checks |
|---|---|---|---|---|
| `census-cps-tables` | [Census voting tables](https://www.census.gov/topics/public-sector/voting/data/tables.html) | Historical national/state registration and self-reported turnout by demographic group. | Held; `data/sources.json`, `scripts/download.py`, `scripts/build.py`. | Preserve year-specific citizen/adult-resident denominator, native age/race bins, suppression and margins. Not county/precinct turnout. |
| `census-cps-microdata` | [CPS Voting and Registration files](https://www.census.gov/data/datasets/time-series/demo/cps/cps-supp_cps-repwgt/cps-voting.html) | Public survey files, technical layouts and weights; 2022/2024 are held. | `data/cps-sources.json`, `scripts/cps.py`. | Preserve noninterviews, unknown/refused answers and full eligible denominator. Survey self-report is not administrative validation. |
| `census-acs-cvap` | [ACS data](https://www.census.gov/programs-surveys/acs/data.html), [CVAP](https://www.census.gov/programs-surveys/decennial-census/about/voting-rights/cvap.html) | Population denominators and geographic demographic context. | Method/denominator source; acquire exact tables/vintage before use. | CVAP is not automatically legal eligibility or registered population; neighborhood attributes are not individual attributes. No product of marginals as observed joint cells. |
| `census-tiger` | [TIGERweb](https://tigerweb.geo.census.gov/arcgis/rest/services) | State/county and other reference geography. | URLs/hashes in `data/sources.json` and companion geometry receipts. | Reference geometry is not proof of election-day precinct boundaries or cross-year identity. |
| `fec-results` | [FEC election results](https://www.fec.gov/introduction-campaign-finance/election-results-and-voting-information/) | Official federal candidate totals and historical state controls. | Held 2020/2024 controls; companion `data/participation-historical-backtest/` and `data/participation-coalition-scenarios/`. | Candidate votes are not ballots cast. Parse candidate columns by headers; preserve fusion/write-in/other treatment and reconcile national/state totals. |
| `eac-eavs` | [EAVS catalog](https://www.eac.gov/research-and-data/studies-and-reports), [interactive data](https://www.eac.gov/research-and-data/studies-and-reports/eavs-data-interactive) | Historical local-jurisdiction turnout, registration and election-administration controls. | Catalog identified; earlier native 2020/2022/2024 dataset/codebook requests returned HTTP 403. Native inputs not held from those attempts. | Preserve question/year definitions and jurisdiction scope. Do not retry denied endpoints through another client, cache or mirror. Aggregate controls do not identify individual transitions. |
| `ncsbe-results` | [NCSBE historical results](https://www.ncsbe.gov/results-data/election-results/historical-election-results-data) | Candidate returns by election, county, precinct and voting method; current ENR also reports ballots/registrations. | Held; `scripts/current.py`; companion `scripts/build-precinct-results.py` and source reviews. | Keep residential precincts distinct from central early/mail/provisional units. `bct`, candidate votes and `rtl` are different fields. |
| `ncsbe-history` | [NCSBE voter history](https://www.ncsbe.gov/results-data/voter-history-data) | Historical participation and linkage definitions. | Historical aggregates held; separately controlled private statewide history work supports adjacent historical benchmarks. | Missing/incomplete history is unknown. Use election-time voted geography where supplied; current registration residence is not past residence. |
| `ncsbe-registration` | [NCSBE registration data](https://www.ncsbe.gov/results-data/voter-registration-data) | Registration statistics, snapshots and public-file definitions. | Historical aggregates and selected private snapshots held. | Current/most-recent registration date is not first-ever registration or first voting. Historical electorates require original frames and removal/mover accounting. |
| `ncsbe-absentee` | [NCSBE absentee/provisional data](https://www.ncsbe.gov/results-data/absentee-and-provisional-data) | Early/mail/provisional counts and source-defined demographic breakdowns. | Held; `scripts/current.py` and private linkage receipts. | Requests, returns, acceptance and counted ballots differ. These counts overlap other totals and are not additive. |
| `state-local-election-offices` | Primary office links in companion [participation reviews](https://github.com/hanshanley/margin_of_error/blob/main/public/participation-source-reviews.json) and [precinct reviews](https://github.com/hanshanley/margin_of_error/blob/main/public/precinct-results.json) | Other state/county results, ballots, registration, reference maps and historical reports. | Full per-source URLs and native clocks in linked reviews, not duplicated here. | Identify source geography, office, election stage, mode and denominator before pooling. Source-row presence is not full statewide coverage. |
| `state-voter-rolls` | Official election-office routes; [EAC access overview](https://www.eac.gov/election-officials/voter-lists-registration-confidentiality-and-voter-list-maintenance) | Current rolls, historical snapshots and participation-history exports, where supplied. | Statewide acquisition route; some are downloads, others requests, fees or requester/use-limited. | Record the actual route, access terms, history window and 2026 posting status. A failed download is not proof of absence. Do not submit orders, attestations or requests without authority. No public identifiers or raw voter records. |

## Historical returns: academic and publisher compilations

| ID | Source | Data / access | Status and caveats |
|---|---|---|---|
| `mit-county-president` | [MIT county presidential returns, DOI VOQCHQ](https://doi.org/10.7910/DVN/VOQCHQ) | National 2000-2024 county presidential source. | Identified. This session's native Dataverse metadata request returned HTTP 403; route stopped. Do not silently substitute a mirror or claim this artifact was acquired. Separately published precinct datasets below are different products. |
| `mit-data-catalog` | [MIT Election Lab catalog](https://electionlab.mit.edu/data) | Discovery for historical federal/state returns and documentation. | Primary catalog for MIT products, not a guarantee of complete precinct coverage in every file. |
| `medsl-2022` | [MEDSL 2022 official returns](https://github.com/MEDSL/2022-elections-official) | Pinned national snapshot `a8126c5790b8d1f438a3e63c3506cdcdc7406d9f`; 51 jurisdiction ZIPs held. | 12,310,863 native rows; 34 checks passed. Missing precincts, higher administrative units, suppression, RCV and reconciliation holds retained. Candidate counts, not turnout. |
| `medsl-2024` | [MEDSL 2024 official returns](https://github.com/MEDSL/2024-elections-official) | Pinned national snapshot `df531089c78e6d0098db1a6bfb3849a066a06995`; 51 ZIPs plus three aggregate CSVs held. | 18,383,653 native rows; 29 checks passed. Snapshot completeness is not complete precinct coverage. Preserve state-specific warnings and negative/suppressed source values. |
| `medsl-older-precincts` | [MIT catalog](https://electionlab.mit.edu/data) | 2016, 2018 and 2020 precinct products and their codebooks. | Discovery/holdings vary by product; check the exact saved manifest before treating a file as held or complete. |
| `openelections` | [OpenElections](https://github.com/openelections) | Standardized state CSVs and original election files. | A 25-state 2022 source batch and other historical originals were already held; this is not the newer all-jurisdiction MEDSL snapshot. File names alone do not qualify contest/mode scope. |
| `nyt-2024-precincts` | [NYT 2024 release](https://github.com/nytimes/presidential-precinct-map-2024) | Held presidential precinct/municipality results and joined geometry for 49 states plus D.C. | Alaska absent from this saved layer; within-state omissions/approximate boundaries remain. Retain the C-UDA and state notes. This is not NYT's underlying demographic voter-file model. |
| `nyt-2020-precincts` | [NYT/Upshot 2020 release](https://github.com/TheUpshot/presidential-precinct-map-2020) | Held original 2020 layer for 46 states plus D.C. | Saved layer lacks AK/AL/LA/VA. Do not replace it with 2020 votes reallocated onto 2024 boundaries or imply a longitudinal crosswalk. |
| `heideman-county-history` | Paul Heideman, U.S. county-level election results; exact native URL/version in companion `data/precinct-source-reviews/20261105-historical-county-bulk-01/acquisition.json` | Pinned `v1.0.0` original, candidate/party and county summary tables; 1990-2024 entries. | Raw archive covers 48 states, excluding AK/HI/DC from this compilation. Preserve upstream per-source rights/quality flags. County-to-state candidate controls expose discrepancies; arithmetic alone is not certification or turnout. |
| `538-historical-results` | Historical FiveThirtyEight returns referenced by the combined compiler below. | Source receipts/paths must be retained for the exact archive used. | Secondary statewide/district histories; not independently validated county data. Never put a statewide total into a county without an explicit administrative-unit label. |

### MEDSL processing rules

1. Read the pinned README and codebook before selecting rows. Keep `TOTAL` once
   where it coexists with components; retain excluded rows and the decision.
2. Keep regular/general, primary, special and runoff elections separate.
   Preserve district/seat, candidate, literal party, write-ins and contest magnitude.
3. Keep county/town/township/VTD and county-only absentee units distinct.
   Never sum parent counties with child towns or allocate county-only votes to precincts.
4. Suppressed `*` is unknown, not zero. Negative correction artifacts are not
   clamped. Missing identifiers and synthetic cross-county codes need explicit holds.
5. Connecticut planning regions are not the historical eight counties.
   Native identifiers and election-date geography determine comparability.
6. Preserve every selected/unselected/withheld source row. Raw source presence
   does not authorize inferred ballots cast, demographic turnout or persuasion.

## Current 2026 returns: exact counts and comparison products

| ID | Source | Retrieval / native fields | Status and automation rule |
|---|---|---|---|
| `civicapi` | [API documentation](https://civicapi.org/api-documentation), [Bauer-Haus/election](https://github.com/Bauer-Haus/election) | Public race JSON, native candidate counts and `region_results`; [Senate index 87528](https://civicapi.org/api/v2/race/87528). | All 35 declared Senate race files held, each HTTP 200: 3,718 native regions; 2,442 county/parish/independent-city records in 34 states, six without FIPS. Follow declared IDs; retain towns/Alaska separately and attribute civicAPI. |
| `cnn-results` | [Texas regular Senate example](https://politics.api.cnn.io/results/county-races/2026-SG-TX.json), [Ohio special](https://politics.api.cnn.io/results/county-races/2026-SP-OH.json), [Alaska](https://politics.api.cnn.io/results/county-races/2026-SG-AK.json) | County-races election-results JSON. Regular `SG` and special `SP` are separate routes. | All 35 files held, HTTP 200, with 3,799 native reporting units. Initial named-candidate/FIPS check: 7,165 equal counts and 215 different counts, plus unmatched source units/candidates. Preserve different clocks and unresolved rounds; not independent outcome validation. Not CNN/SSRS Voter Poll files. |
| `pushbuild-2026` | [Project](https://github.com/pushbuild/us-2026-election-results), [data](https://github.com/pushbuild/us-2026-election-results/tree/main/data) | National secondary county/candidate CSVs and source references. | Complete snapshot `56b4b499507f5b8fce9433640de34a56df4ad619` held: 40 state CSVs, 127,870 native rows, all 42 repository blobs verified, CC0. Includes candidate-list placeholders, not just results; no missing-as-zero. Native README count time is 2026-11-06 23:32 Eastern. |
| `mike-county-shifts` | [Project/methods](https://github.com/mike10010100/elections-2026), [county JSON](https://raw.githubusercontent.com/mike10010100/elections-2026/main/site_data/county_shifts.json) | `h24`/`h26`, `s20`/`s26`, other cycles; `d/r/i` percentages and `v` contest votes. | Snapshot and verified fields below. Secondary NYT/civic/history combination, not independent gold. Never reconstruct exact candidate counts from rounded shares. |
| `transparency-cascade` | [Methods/map](https://transparencycascade.org/maps/2026-county-swing/), [Senate comparison CSV](https://raw.githubusercontent.com/TransparencyCascade/TransparencyCascade.github.io/main/static/data/2026-midterms/county-swing-2026-senate-vs-2024-president.csv) | Secondary Senate-vs-2024-president county comparison with candidate counts. | Complete native CSV held: 2,179 rows in 30 states, rather than the earlier user-reported 2,177. Preserve this exact snapshot, native notes and omitted non-major-party races; derive any narrower usable subset explicitly. |
| `rohe-governor` | [Karl Rohe governor CSV](https://pages.stat.wisc.edu/~karlrohe/lr333/governor_2026.csv) | `dem_2022`, `rep_2022`, `dem_2026`, `rep_2026`, FIPS, candidates and `pct_in_2026`. | Held: 2,014 records, 28 states independently counted; native Last-Modified 2026-11-04 20:21:13 GMT. Validate geography and integer values before aggregation. This is a D/R subset of contest votes, not ballots or all candidates. |
| `carmena-precincts` | [Carmena's Overton](https://carmenaresearch.com/election-data/precinct-level-data/) | User-provided commercial/arrangement-based precinct lead. | Lead only; no order, agreement, access or nationwide coverage is assumed. Do not automate gated acquisition. |
| `uf-turnout` | [UF Election Lab](https://election.lab.ufl.edu/) | Preliminary/historical state turnout totals, denominator estimates and documentation. | Pinned reviewed files in companion `public/uf-turnout.json` and source archives. Preserve CC-BY attribution, versions, native `Initial Estimate`, and unresolved codebook definitions. State estimates are not certified local ballots. |

### Verified combined-JSON snapshot

At commit `9826604164cd4291739274ba34b1091a105e1400` of
`mike10010100/elections-2026` (commit time 2026-11-08 00:31:05 UTC):

| Item | Observed records |
|---|---:|
| All JSON entries, including historical-only entries | 3,143 |
| Nonempty positive-vote `h26` records | 3,111 |
| Records with both `h24` and `h26` | 3,083 |
| Nonempty positive-vote `s26` records | 2,443 across 35 states |
| Records with both `s20` and `s26` | 2,287 |

The full JSON SHA-256 is
`c412b09090c289e4825d2368c6582912811b264a65c302a0f13b3dc6aa973292`.
These are **record-presence counts**, not approval of every county comparison.

- Alaska's `02020`/Anchorage record contains statewide hub totals and historical
  statewide backfills. Do not count it as Anchorage County/Borough returns.
- The builder can copy Connecticut planning-region totals to multiple historical
  counties. Hartford/Tolland duplication is present in the saved snapshot.
  Hold Connecticut county comparisons until a valid crosswalk/reaggregation exists.
- `v` is votes in the selected race, not ballots cast or unique participants.
  `ev`, `rem` and `eevp` are source expected-vote/reporting quantities, not eligible
  population denominators or measured nonvoters.
- `d/r/i` are percentages. Historical shares may have lower precision than 2026
  shares; do not recover purported exact candidate counts by multiplication.
- `op` flags a one-major-party comparison; `m` is the compiler's D-minus-R
  percentage margin, not necessarily the margin between the two leading candidates.
  Nebraska independent support remains in `i`; do not turn Dan Osborn into a Democrat.
- Keep House, Senate and governor separate. Do not substitute `top26`, which can
  mix offices across states, for a same-office national panel.
- For regular Senate same-seat comparison, inspect `s20`/`s26` against the
  [official Senate classes](https://www.senate.gov/senators/Class_II.htm).
  Florida/Ohio 2026 specials need their own seat/baseline contracts.
- Do not call agreement with another NYT/civic-derived product independent
  validation; shared upstream feeds must retain a common source-family identity.

## Surveys, participation histories and vote-choice evidence

The core public collectors remain aggregate-only. The separately supplied
respondent-level studies below are private analysis inputs; they are not added
to the public research export merely because this ledger records them.

| ID | Primary producer / study | Holdings and use | Important limits |
|---|---|---|---|
| `ap-votecast-history` | AP/NORC VoteCast 2018, 2020, 2022 and 2024 public-use files supplied locally | Data/codebooks/questionnaires/SAS labels held. State and national `POLLCLOSE`/`FINALVOTE` weights target the full study registered-voter frame. | Repeated releases are not a released linked panel. `LIKELYVOTER` is modeled/self-reported, not administrative turnout. Final weights calibrate current results. Preserve form/routing blanks, unknowns and disclosure removal. |
| `norc-chep-2026` | [NORC Civic Health & Elections Project](https://civichealth.norc.org/) and user-supplied Civic files | CSV/data ZIP/codebook ZIP held and privately checked; 113,020 respondents in 50 states, no D.C. `CHEP_WEIGHT`, prior 2024/2022 participation/choice, current likelihood and model classes present. | Questionnaire dated 2026-10-16 is not a field period. Full weight target/calibration and fieldwork metadata are not in the supplied local documentation. Current answers mix already-voted and intended voting. No automated site download or raw redistribution permission is inferred. |
| `ssrs-voter-poll` | [SSRS methodology](https://ssrs.com/wp-content/uploads/The-Voter-Poll-by-SSRS-Methodology-Statement_Final.pdf), CNN/NBC/AP partner Voter Poll presentations | Qualified selected 2026 current-voter joint tables and demographic questions held in companion survey packages. | Partners share the study, not independent samples. Current-voter-only tables cannot directly measure prior voters staying home. Preserve recontact/retained pre-election answers, suppression, candidate identities and actual state coverage. D.C. not sampled. |
| `ces-common` | [CES 2024, DOI X11EP6](https://doi.org/10.7910/DVN/X11EP6), separately qualified CES 2022 common release | Private source data; public-safe selected aggregates/code in companion historical and demographic review tools. | Use each release's native labels/weights/state encoding, not display order. Missing administrative matches are unknown. Current registrant/resident frames are not original electorates. |
| `ces-panels` | [2020-2022 panel, DOI XV7ABM](https://doi.org/10.7910/DVN/XV7ABM), [2020-2024 panel, DOI CETPVT](https://doi.org/10.7910/DVN/CETPVT) | Paired survey diagnostics and selected history matrices already computed. | Attrition, source-weight targets, older-choice verification and missing history remain explicit. Do not rebrand selected-panel recall accuracy as population validation. |
| `ces-cumulative` | [Cumulative CES, DOI II2DB6](https://doi.org/10.7910/DVN/II2DB6) | Additional user-supplied historical lead for pre-2018 turnout/choice. Native acquisition/variable qualification not completed. | Verify actual version/year coverage and native historical labels, validation and weights before using the advertised 2006-2025 range. DOI rendering failed separately; the previously untried native metadata endpoint `https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/II2DB6` then returned HTTP 403 on November 8, 2026 at 03:54:39 UTC. This exact route is stopped, not retried through another client, cache or mirror. No dataset or native guide was acquired. Receipt: active session `ces-cumulative-native-discovery-20261108-01/receipt.json`. |
| `ces-2026-schedule` | [Tufts methodology/schedule](https://tischcollege.tufts.edu/research-faculty/research-centers/cooperative-election-study/about-methodology), [public downloads](https://tischcollege.tufts.edu/research-faculty/research-centers/cooperative-election-study/data-downloads) | Schedule reviewed: November 2026 post-election fieldwork, March 2027 team data, summer 2027 voter-file-matched team data. | Team delivery dates are not public release dates. No present 2026 respondent file is held; do not delay current Civic-based estimates waiting for it. |
| `anes-cumulative` | [ANES time-series cumulative file](https://electionstudies.org/data-center/anes-time-series-cumulative-data-file/) | Additional historical lead; native cumulative file/weights have not been qualified. | An earlier optional ANES landing returned HTTP 403. That attempt remains stopped; no unauthorized mirror, bypass or fabricated analysis. |
| `pew-validated-voters` | [2024 methodology](https://www.pewresearch.org/politics/2025/06/26/validated-voters-2024-methodology/), [2022 release note](https://www.pewresearch.org/decoded/2024/10/31/validating-2022-voters-in-pew-research-centers-survey-data/) | Public methodological/aggregate benchmarks. | Respondent data require the actual permitted access route. Frame/weights/matching and outcome calibration differ; unmatched public percentages are not state-level ground truth. |
| `pew-2026-intentions` | Pew ATP Wave 200; exact article/questionnaire/receipt links in companion `data/participation-pew-intentions/` | Qualified factual selection from a pre-election registered-voter study; original documents remain private. | Intended House choice, not completed 2026 participation; historical turnout validation does not validate current intentions. |
| `mevp-bsp-aarc` | BSP/AARC Midterm Election Voter Poll; exact primary receipts in companion `data/participation-mevp/` | Selected broad national racial-group prior/current-choice tables held. | Mixed early reports/intended voting; restricted prior-choice routing. First-November voting is not first-ever voting. Do not scale restricted prior shares as unconditional electorate composition. |
| `slu-missouri` | Saint Louis University/YouGov Missouri August 2026 study; receipts in companion `data/participation-slu-intentions/` and demographic package | Earlier likely-voter intentions with actual joint questions. | August intentions, not November outcomes; source-native groups/geographic context are not automatically cross-source demographic matches. |
| `prolific-recontact` | Prolific October 2026 study and pre-election recontact; private source receipts | Native articles, questionnaires and aggregate workbooks held. | Already-voted respondents and recontact-only universes differ; published participation and choice marginals are not an exported joint table. Public redistribution basis remains unqualified. |
| `democracy-corps` | [Democracy Corps](https://democracycorps.com/) November 2026 release | Native topline/method reading held privately. | No qualified prior/current joint tables or state/nonvoter universes established by that release; not a missing-state solution. |
| `state-poll-leads` | OPB/DHM Washington, Utah Political Trends/NPI, Bowen/Indiana and other state-specific leads in source receipts | Screened discovery or private originals, with explicit per-study dispositions. | Do not multiply disconnected marginals or substitute pre-election intentions for completed participation. A blocked individual file is not global data absence. |
| `yougov-permission` | YouGov post-election release/license/terms lead | Native acquisition held at an observed source-specific permission gate. | Do not use another host/partner/cache to bypass the gate or assume all unrelated publishers are prohibited. |
| `l2-marginals` | L2 aggregate turnout/first-record report, source receipts in completed historical reviews | All-state historical one-year marginals were qualified. | Marginals are not linked transitions; first record since a source window is not first-ever voting. Vendor-modeled demographics are not measured attributes. |
| `states-united-reports` | States United public reports, exact primary report links in historical evidence receipts | Selected factual claims retained; incompatible-cohort derived overlaps quarantined. | Do not manufacture a common-cohort transition from differently defined annual, transition or proxy groups. |

### User-supplied survey archive handling

- Historical files: `AP_VOTECAST_2018_DATA.zip`,
  `AP VoteCast 2020 Public Use Files.zip`,
  `2022 General Election Public Use Files and Codebook.zip`,
  `AP_VOTECAST_2024_GENERAL_4.10.2025.zip`.
- The second 2022 `(1)` archive is byte-identical: process it only once.
- The 2020 outer archive contains separate general-election and Georgia-runoff
  packages. Never concatenate them into one general-election sample.
- Civic files: `civichealth_codebook.zip`, `civichealth_datafile.zip`, and the
  equivalent standalone CSV. Use one CSV, not multiple format copies as samples.
- Keep original local paths in private configuration/receipts, not this public ledger.
  Never commit respondent records, identifiers, private fine cells or session cookies.
- AP CSVs use formatted labels; Civic core fields use numeric codes, sometimes
  serialized as decimal strings. Read the included native dictionary/SAS labels.
- Separate 50-state sample presence from qualified published state inference.
  The [2018 AP study page](https://apnorc.org/projects/ap-votecast-2018/) reports
  electorate estimates in 47 states with statewide races. Do not promote the
  other states solely because a weight column has positive mass. The supplied
  2022 documentation excludes Delaware/West Virginia from state inference even
  if state weights have positive mass. Use the correct weights and full frame.
- Civic `TURNOUT_2024` is county context, not individual history. The supplied
  CSV and Excel dictionaries reverse low/high labels; withhold that mapping.
- Disclosure code 88 is not zero or a recoverable missing category.
  `FTVOTER` can mean first **general** election, with routing/form restrictions;
  it does not establish first-ever voting or newly eligible status.
- Do not link the releases by `SU_ID` without an actual longitudinal contract.
  Nonmissing choice is not universally a completed vote, and modeled nonvoter
  is not measured staying home.

### Current derived analyses and remaining reconciliation

- AP 2018/2020/2022/2024 numerical estimates are computed from 532,866 source
  records: 12,024 full-frame aggregate rows, preserving poll-close/final and
  state/national weights. An independent native reader passed 132,196 checks.
  Maintained code is `scripts/ap_votecast_estimates.py`; private outputs are
  version `ap-votecast-participation-estimates-05`. Native 2018 CSV uses
  Windows-1252; other waves use UTF-8. State labels carry postal prefixes,
  not FIPS. Documented `RACETH5` is absent from the released 2022 CSV and is
  explicitly withheld, not reconstructed from another field. The `weight_field`
  source-variable name is distinct from numeric `weight` mass.
- Public AP selection `data/ap-votecast-aggregates/20261108-01/` uses only those
  already verified cached statistics, not another native reduction. Its
  [immutable complete AP ZIP](https://github.com/hanshanley/margin_of_error/releases/download/participation-ap-history-20261108-01/complete-analysis.zip)
  has 9 members, 236,316 bytes and SHA-256
  `dbab5b50a99882780ae8febe76f564acebc3b1acaf7ef23f3b21aa0693a58190`.
  All five release assets were authenticated-draft and anonymous-published
  byte-verified; the published release is immutable. It includes 602 selected
  participation rows (218 national, 384 whole-state overall), all 710 broad-query
  dispositions, every permitted selected input, viewer JSON, source hashes,
  code and tests. Eight focused tests and 29,172 independent cached-selection
  and Fraction-rate checks passed; blocked-network/DNS/external-command
  reproduction under two hash seeds byte-matched every member and the ZIP.
  Private state demographic cells, respondent records and identifiers remain
  excluded. The whole-state/national support screens use total positive-weight
  cases only, not unrecorded per-outcome raw counts or a precision/anonymity
  guarantee. Native group definitions and four weight frames remain separate;
  2018 state inference qualifications, 2022 DE/WV holds and absent 2022 RACETH5
  are retained. The historical view is now live in the existing folded research:
  website main `3827eb47a72f9152aec8805742fee2c6d9c86688`, Pages run
  `42441500031`, attempt 1, fresh artifact `13601962258`. All 14 production
  modes passed, including every public AP row and the valid-JSON changed-byte
  checksum failure. Native uploaded/deployed identity, actual 997,463,197-byte
  payload and 999,976,960-byte tar, full asset bytes, served HTML/scripts and
  source pointers passed. All 3,055 prior links/IDs remain; complete downloads
  total 1,057. The 339,721-byte public viewer JSON is pinned to research commit
  `3a9d85994e59a6112d3756ef1f7f0ea15038a135`, has verified CORS support and
  is checksum-verified before client use. No private fine cells are fetched.
- The supplied Civic file now has actual private numerical outputs for all
  50 states plus a separately labeled pooled-source scope: 1,954 participation
  rows, 97,700 complete joint cells, 3,908 margin decompositions and 30,782
  likelihood cells. An independent native pandas/Decimal reader passed
  246,204 count, weight and formula checks without importing the estimator.
  These are exploratory/source-weighted estimates, not population certification.
- House comparison version `national-house-comparison-20261108-02` preserves
  all 3,143 source records and 3,083 positive-vote pairs. Of these, 2,776 pass
  the known Alaska/Connecticut/uncontested screens. Its separate exact
  Pushbuild House query contains 8,509 candidate rows in 35 states; no exact
  candidate counts are inferred from the combined JSON's rounded shares.
- Exact House join `house-exact-panel-20261108-03` separately uses the actual
  reviewed 2024 MEDSL-origin candidate lines and 2026 county-district-candidate
  counts from companion snapshot `20261107T125502Z`, pinned to website commit
  `96cc899f6b1266baf6316a923ad9117cd5526e97`. Its complete query has 3,152 county
  records, 2,639 positive-count pairs, 2,228 known-screen passes in 38 states,
  5,192 county-district rows and all 1,418 candidate controls. It preserves six
  withheld historical candidate rows, 34 historical unopposed/no-ballot records,
  literal-party/group mismatches, fusion labels and unknown district boundaries.
  The independent SQLite/Fraction verifier passed 124,804 native checks.
  Maintained `scripts/house_panel.py` has nine focused tests; the complete
  [immutable House ZIP](https://github.com/hanshanley/margin_of_error/releases/download/participation-house-exact-panel-20261108-01/complete-analysis.zip)
  is 1,466,353 bytes, 18 members, SHA-256
  `8203d46e5ff10ce894aca498deb2558f783d261a116f2dac0311e58e8563c567`.
  It includes all six pinned aggregate inputs, full queries, exclusions, code
  and tests; all eight release assets were authenticated-draft and
  anonymous-published byte-verified, and the published release is immutable.
  Offline reproduction blocks network/DNS/external commands and byte-matches
  every member and the complete ZIP under two hash seeds. Exact contest counts
  are not ballots, turnout, individual switching or complete-source certification.
- Senate initial controls retain every native candidate unit. The follow-up
  `senate-cross-source-reconciliation-02` explains four Rhode Island gaps with
  its explicit 755-vote Overseas/Federal bucket. This is not a county allocation.
  There are now 229 matching candidate controls, four Alaska noncounty holds,
  and one Maine write-in control with 882 state votes but zero in the supplied
  county vectors. Preserve that unresolved scope instead of filling counties.
- The six source-missing county IDs are now separately reference-joined by
  `scripts/senate_geography.py`: MN `27073`, `27077`, `27085`; MT `30049`;
  OK `40079`; SD `46102`. Held Census-backed House namespace records and
  CNN declared county IDs corroborate each join, and all named Senate
  candidate identities agree. The reference derives from the previously
  checked complete [2026 TIGER county release](https://www2.census.gov/geo/tiger/TIGER2026/COUNTY/);
  it was reused, not downloaded again. Original blanks remain in `fips`;
  `resolved_fips` and `fips_resolution` identify the derived references.
  All 34,492 source rows/fields/votes/clocks are unchanged, with 26 civic
  candidate rows receiving reference IDs. Of 23 additional named-count pairs,
  22 agree and one difference remains. This is not independent outcome or
  same-round validation. The
  [complete immutable Senate identifier ZIP](https://github.com/hanshanley/margin_of_error/releases/download/participation-senate-identifiers-20261108-01/complete-analysis.zip)
  has 12 members, 956,205 bytes, SHA-256
  `1c3938ea0d933d7e9fd628d07b0d3244c76fa795a18ac1bb21692a11a771d7ef`.
  All five release assets were authenticated-draft and anonymous-published
  byte-verified. Six tests, 69,225 independent preservation/reference checks,
  and offline reproduction under two hash seeds matched every member and
  the ZIP with network/DNS/external commands blocked. The Maine 882-write-in
  gap, Alaska/Connecticut geography exceptions and original count/round
  differences remain explicit, not allocated or silently replaced.
- Conditional current-register control comparison
  `state-participation-control-comparison-20261108-02` uses only verified public
  Civic aggregates, the pinned published `20261108T023946Z` nationwide reporting
  snapshot, eight reviewed 2026 observations, UF initial estimates and exact
  House state context. The
  [complete immutable control/scenario ZIP](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-01/complete-analysis.zip)
  has 15 members, 447,129 bytes, SHA-256
  `f7693b54cee3d3e05b809bee92433fc179545c88beedfbadf95858075d5c2482`.
  All five release assets were authenticated-draft and anonymous-published
  byte-verified. It retains all 51 state/D.C. query rows and all 12 native
  control observations, selects seven state references without double-adding
  the NC source, and excludes four county controls from state model allocation.
  Five `R*p`/`R*(1-p)` registration-frame scenarios (AL/CA/CO/NC/OR) are
  explicitly conditional on unvalidated survey/frame exchangeability.
  Only AL/NC/OR have reported cast-ballot measure comparisons; CO returned/
  processed and CA native `voterTurnout` remain different measures. UF's
  estimated VEP never fills a registered denominator, and House candidate
  votes remain context rather than ballots. Source weight target/calibration
  and field period remain unqualified; no national/original-cohort population,
  measured staying-home, partisan fitting or confidence interval is inferred.
  Eligibility/death/migration remain null. Seven tests and 439 independent
  Fraction/scope/archive checks passed, and two blocked-network/DNS/external-
  command reproductions matched all members and the full ZIP. Maintained code:
  `scripts/participation_controls.py`.
- Expanded state/control comparison
  `state-participation-control-comparison-20261108-03` reuses those six frozen
  public inputs and a complete 74-member source bundle from already-held
  Minnesota/Hawaii/Wyoming releases. Its
  [complete immutable version 02 ZIP](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-02/complete-analysis.zip)
  has 17 members, 14,976,527 bytes, SHA-256
  `500ba05dcaa88dea80b543f76479b7590605fa008744c699868b9b7c8b394019`.
  All six assets in immutable release `438017771` were authenticated-draft
  and anonymous-published byte-verified. All 51 state/D.C. rows, 15 native
  observations, nine state references and six scenarios are retained.
  Hawaii uses the explicit statewide PDF/text summary: 365,897 ballots,
  853,399 registrations, REPORT 3, printed November 4, 2026 at 09:09:04 a.m.,
  uncertified. The 496 native units sum to 365,903 ballots; the six-ballot
  difference, zero native registrations and precinct rate holds remain.
  State registration repeats across contest rows and is never added.
  Wyoming's separate 191,688 ballots reconcile across 23 counties and 432
  precincts, but no registration denominator or common statewide update
  clock is invented. Its retained Washakie candidate-category conflict does
  not alter ballot counts. Minnesota's held `20261105-expansion-01` file
  contains 4,105 native statistics rows, only 2,490 flagged reported, and 15
  ballot-mode discrepancies. The complete 1,224,405-ballot and 3,986,420-
  registration-unit sums remain explicitly partial, never statewide controls
  or state survey allocation targets. Source clocks are not acquisition times.
  The sufficient-source bundle retains original aggregate files and public
  source-bound qualified units; acquisition HTTP session headers are excluded.
  Its native provenance pins are HI `b01c32e84cb6346e6478f80c404eb82ec3e6bc7b`,
  WY `6ff31fc2cf9a4be6757db120b8ab2df3a08f7cb5` and
  MN `a81e721f4a013d5bd00e4e65825b101f501c9503`.
  Hawaii adds the sixth conditional scenario; Wyoming remains ballot-only.
  The prior five scenarios, 49 unaffected state rows and 12 old controls
  remain unchanged. Twelve tests and 5,530 independent Fraction/source/scope/
  preservation/archive checks passed. Both blocked-network/DNS/external-
  command reproductions matched every member and the whole ZIP. Version 01
  remains immutable; no new website deployment is claimed for version 02.
- Additional held-source version
  `state-participation-control-comparison-20261108-05` is published in
  [immutable version 03](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-03/complete-analysis.zip),
  native release `438022113`. Its 20-member ZIP is 20,124,248 bytes, SHA-256
  `bbc3e125b1cfb53e7b482673c5eacff78150909e53f7e56e890d6548df9d332e`.
  All seven assets were fully byte-verified before and after publication.
  Complete outputs now retain 51 state/D.C. rows, 19 observations, 13 state
  references and eight conditional scenarios. The new 42-member sufficient-
  source bundle uses the already-held VT/ID/RI/DC count reviews in website
  revision `3827eb47a72f9152aec8805742fee2c6d9c86688`, with original aggregate
  JSON/XLSX/PDF/XML/CSV, native qualified units and source-frame definitions;
  no acquisition session headers or compiled publisher app code is exported.
  Vermont's 247 municipalities supply 506,512 source registrations and
  311,009 native "Votes Cast." The latter are not silently promoted to cast
  ballots. Its 311,429 House accounting total, five municipal accounting
  differences and Colchester's split-scope difference remain.
  Rhode Island's explicit parent `totalVoters` is 794,266, independently equal
  to its 40 locality registration fields and the native registration table.
  Its parent `ballotsCast` is zero while all 39 municipalities plus the Federal
  unit total 364,082 ballots: do not use that parent zero as statewide turnout.
  The Federal unit's 756 ballots and zero registration remain unchanged.
  Native active/inactive semantics stay unqualified; no Federal registration
  is fabricated or votes geographically allocated. This source clock is
  distinct from the earlier 755-vote Senate observation.
  Idaho's separate ballot report supplies 731,980 ballots across 44 counties/
  986 units. Its 1,055,089 native registration-unit sum remains context, not a
  state denominator: Twin Falls workbook/API counts 41,878/42,990 disagree.
  Seven House/ballot-report differences, eight pooled reporting units and
  all rate holds remain. D.C.'s 144 precinct rows sum to independently reported
  citywide 185,086 ballots and 457,371 registrations, with outstanding ballots,
  registration-date qualification and local-contest accounting differences
  retained. There is no D.C. Civic estimate or survey allocation.
  New conditional scenarios are RI and VT; all six preceding scenarios,
  47 unaffected state rows and all 15 preceding controls remain unchanged.
  Sixteen tests and 1,953 new independent source/Fraction/scope/preservation/
  archive checks passed. Both network/DNS/external-command blocked reproductions
  matched every member and the full ZIP. Prior versions and their proofs remain
  immutable. Version 05 supersedes the private preliminary version 04, which
  withheld RI registration before the explicit parent field was checked.
  No new website deployment is claimed.
- Complete private outputs/receipts and executed code remain in the active
  session artifact workspace under those versioned names and
  `survey-reconstruction-all-states-20261108-01`. They are not already published
  website assets. The complete permitted 98,019-byte ZIP and four CSV supplements
  are now published in immutable companion release
  `participation-civic-estimates-20261108-01`. Its initial accepted folded
  research revision was `96cc899f6b1266baf6316a923ad9117cd5526e97`,
  Pages run `42438745610`, attempt 1, fresh artifact `13600852929`.
  Native uploaded/deployed artifact identity, both strict actual payload/tar
  caps, all 13 production browser modes, full Civic downloads and served
  HTML/scripts/source pointers passed. All 1,047 old complete links and IDs
  remain, with five complete Civic assets added. The newer accepted AP revision
  preserves this component and rechecks its four production modes. Maintained code is now
  `scripts/civic_estimates.py` with focused
  tests; it refuses fine-grained output inside Git repositories. The original
  executed source/test/verifier bytes are preserved with the private result.
  Matched participation controls and remaining source exceptions are tracked
  in [REMAINING.md](REMAINING.md); these increments are not a claim that the
  nationwide project is finished.

## Access, methodology and paid/reference-only leads

**Washington direct access holds, November 9, 2026 UTC:** the
[official elections index](https://www.sos.wa.gov/elections) and distinct
[official results product](https://results.votewa.gov/) each returned HTTP403
with a 17-byte plain-text body. Saved receipt times are
01:13:08.738162+00:00 and 01:13:58.791834+00:00 respectively; both body SHA-256
values are `2938e9f1284180959e33ab1718d0793a72ff6e4cdb8108c34dcd14e69446de5c`.
Both routes are stopped, without another client, cache or mirror. This is an
access hold, not evidence that statewide data do not exist; no county sum or
earlier-election register substitutes for a missing statewide source frame.
The separate already-held snapshot above supplies an explicit registration
parent only; it does not reopen these routes or supply observed state ballots.

| ID | Source | Role / rule |
|---|---|---|
| `nvra-records` | [52 U.S.C. 20507](https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title52-section20507&num=0&edition=prelim) | Federal inspection/list-maintenance reference; not a blanket promise of a free unrestricted downloadable roll. |
| `ncsl-voter-lists` | [NCSL state access comparison](https://www.ncsl.org/elections-and-campaigns/access-to-and-use-of-voter-registration-lists) | Secondary discovery for fees/requester/use restrictions. Verify current primary state requirements before acquiring or submitting anything. |
| `senate-seat-classes` | [U.S. Senate Class II](https://www.senate.gov/senators/Class_II.htm) | Primary seat-cycle reference. Same-office does not automatically mean same seat or same election stage. |
| `leip-atlas` | [Dave Leip's Atlas store](https://uselectionatlas.org/BOTTOM/store_data.php) | Paid historical county-return lead. No purchase, license or access is assumed. Prefer already held/free qualified bulk inputs first. |
| `ecological-identification` | [Forcina/Pellegrino](https://arxiv.org/abs/1411.4411) | Aggregate totals do not uniquely identify individual switching/nonvoting; model assumptions and validation remain necessary. |
| `survey-nonresponse` | [Tang/Hillygus/Reiter](https://arxiv.org/abs/2209.05220) | Methods reference for turnout nonresponse/weighting; not evidence that the current project implements or validates that procedure. |
| `medsl-methods` | [MEDSL collection/QA methods](https://arxiv.org/abs/2106.04570) | Academic description of data collection and processing; preserve state-specific source caveats too. |
| `nyt-voter-trends-method` | [User-provided 2026 methodology](https://www.nytimes.com/2026/10/25/us/elections/times-voter-trends-methodology.html), [2024 interactive](https://www.nytimes.com/interactive/2024/elections/voter-trends-national.html) | Methodological references, not an acquired underlying NYT voter-file/demographic model. Do not claim to reproduce proprietary inputs. |

## Automation contract

For each new source family, add a stable ID here and record these fields in its
machine receipt:

1. Publisher, primary/secondary class, upstream family, dataset/office/election
   identity, seat/stage/round, geography/unit, voting modes and denominator.
2. Declared entry point and resolved native URL; repository commit/tree/blob or
   dataset DOI/version/file ID; retrieval UTC and native clock/timezone separately.
3. HTTP status, complete byte count, SHA-256, native checksum/Git blob where
   provided, source license/use terms and access method.
4. Scope/selection rules, every omitted/unknown/suppressed unit, count and
   geographic checks, controls and signed discrepancies.
5. Full original and complete permitted query outputs, not metadata-only exports.
   Private/restricted inputs must remain outside public Git/releases.
6. Collector/parser and focused test command, exact output paths, refresh policy
   and what changes require a new version or manual review.

Historical releases are immutable: reuse verified originals and fetch a new
version only when the publisher changes it. Live feeds get new dated snapshots;
never overwrite old bytes or silently blend clocks. Do not execute a downloaded
third-party builder to collect data; review its code and write controlled adapters.

Before calling a result reconciled, check matching office/seat/round/candidate,
native geography and snapshot clocks. Preserve differences rather than fitting
counts, renormalizing shares, clamping negatives, or treating missing as zero.
No current-voter raking back to historical partisan composition.

### Existing collectors and inventories

| Purpose | Existing command / inventory |
|---|---|
| Historical public Census/NC inputs | `.venv/bin/python -m scripts.download`; `data/sources.json` |
| CPS public-use input audit | `.venv/bin/python -m scripts.cps`; `data/cps-sources.json` |
| NC current aggregate snapshot | `.venv/bin/python -m scripts.current --update-downloads` |
| Nationwide aggregate snapshot | `.venv/bin/python -m scripts.nationwide --update-downloads` |
| Restore archived public inputs | `.venv/bin/python -m scripts.restore`; `data/backups.json` |
| Source-specific website registries | Companion `public/precinct-results.json`, `public/county-results.json`, `public/participation-source-reviews.json`, `public/historical-house-counties.json`, `public/uf-turnout.json` |
| Historical county/precinct availability | Companion `public/precinct-coverage.csv`, historical county year/state coverage tables and their original acquisition manifests |
| Newly acquired MIT national snapshots | Private `medsl-2022-national-baseline-01/` and `medsl-2024-national-baseline-01/acquisition-01/` receipts, parsers and complete derived queries; migrate only public-safe artifacts after qualification |
| Supplied survey capability/weight contracts | Private `user-provided-survey-readiness-01/` and per-study codebook/source receipts; raw files remain private |
| New 2026 exact-count comparisons | Private `senate-civic-exact-20261108-01/`, `senate-cnn-exact-20261108-01/`, `pushbuild-national-2026-01/`, `user-2026-county-comparison-01/` |
| Exact historical/current House join | `python3 -m scripts.house_panel --website-root "$EXACT_WEBSITE_CHECKOUT" --output "$NEW_OUTPUT"`; or unpack the complete immutable release and use `--inputs .` for offline reproduction. Full inputs, query/dispositions/control tables and source manifest are included. |

### Exact additional links supplied by the user

These are source references, not instructions to re-download already held files:

| Source | Native entry points / downloads |
|---|---|
| Civic 2026 | [CSV](https://civichealth.norc.org/downloads/civichealth_datafile.csv), [data ZIP](https://civichealth.norc.org/downloads/civichealth_datafile.zip), [codebook ZIP](https://civichealth.norc.org/downloads/civichealth_codebook.zip), [crosstabs](https://civichealth.norc.org/crosstabs.html), [measures](https://civichealth.norc.org/about.html), [release/weighting notes](https://civichealth.norc.org/download-data.html) |
| AP VoteCast 2024 | [Study](https://apnorc.org/projects/ap-votecast-2024-general-election/), [data/codebook ZIP](https://www.norc.org/content/dam/norc-org/datasets/AP_VOTECAST_2024_GENERAL_4.10.2025.zip) |
| AP VoteCast 2022 | [Study](https://apnorc.org/projects/ap-votecast-2022/), [data/codebook ZIP](https://www.norc.org/content/dam/norc-org/datasets/2022%20General%20Election%20Public%20Use%20Files%20and%20Codebook.zip) |
| AP VoteCast 2020 | [Study](https://apnorc.org/projects/ap-votecast-2020-general-elections/), [data/codebook ZIP](https://www.norc.org/content/dam/norc-org/datasets/AP%20VoteCast%202020%20Public%20Use%20Files.zip) |
| AP VoteCast 2018 | [Study](https://apnorc.org/projects/ap-votecast-2018/), [data/codebook ZIP](https://www.norc.org/content/dam/norc-org/documents/standard-projects-pdf/AP_VOTECAST_2018_DATA.zip) |
| AP 2017 pilots | [Publisher write-up](https://www.ap.org/the-definitive-source/products-and-services/beyond-exit-polls-a-new-way-to-survey-voters/) - not a held nationwide respondent file |
| Minnesota 2026 | [House precincts](https://electionresultsfiles.sos.mn.gov/20261103/ushousepct.txt), [turnout/registration](https://electionresultsfiles.sos.mn.gov/20261103/pctstats.txt), [all files](https://electionresults.sos.mn.gov/Select/MediaFiles/Index?ersElectionId=201), [layout](https://electionresults.sos.mn.gov/Results/MediaFileLayout/Index?erselectionId=201) |
| Hawaii 2026 | [Statewide precinct text](https://elections.hawaii.gov/wp-content/results/2026%20General/media.txt) |
| Wyoming 2026 | [Official county precinct reports](https://sos.wyo.gov/Elections/Docs/2026/2026GeneralResults.aspx) |
| Wayne County, MI | [Precinct Excel downloads](https://www.waynecountymi.gov/Government/Elected-Officials/Clerk/Elections/Election-Results-Candidates/November-3rd-2026-General-Election) |
| King County, WA | [Precinct downloads](https://kingcounty.gov/en/dept/elections/results/2026/november-general) - check actual release rather than treating announced dates as completed acquisition |
| San Mateo County, CA | [Results/download instructions](https://smcacre.gov/elections/november-3-2026-election-results) |
| Monroe County, FL | [Precinct reports](https://enr.electionsfl.org/MON/4109/Reports/), [Florida statewide precinct archive](https://dos.fl.gov/elections/data-statistics/elections-data/precinct-level-election-results) |

These are manual command references, not authority to start unrelated workflows.
The user **explicitly restored** the recurring assistant continuation on
2026-11-08 UTC after previously stopping it. See [REMAINING.md](REMAINING.md);
the continuation must proceed into estimates and tested integration, not end at
acquisition. This document itself does not enable a cron job or website workflow.
