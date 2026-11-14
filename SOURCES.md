# Voter-participation source ledger

Ledger updated: 2026-11-14 UTC. Source-specific clocks remain as recorded.

**Start here:** [Overview](README.md) | [Estimation methods](METHODOLOGY.md) |
[Complete downloads](docs/DATA.md) | [Reproduce](docs/REPRODUCING.md).
This document is the detailed reference ledger, not the methods introduction.

| Reference area | Jump to |
|---|---|
| Nationwide swing correction | [All-state source audit and neutral comparison holds](#nationwide-house-display-comparability-correction) |
| Automatic current-results intake | [Hourly GitHub updates, retained source dates and complete numerical queries](#2026-automatic-current-results-intake) |
| Current Tennessee/Montana native observations | [Three county reports, 57 table-only reporting rows and complete numerical SDKs](#2026-tennessee-and-montana-partial-native-participation) |
| Current Kansas official source observation | [Greeley source-reported turnout, explicit partial coverage and complete replay](#2026-kansas-greeley-official-source-turnout) |
| Mississippi publication hold | [Unverified declaration mapping; accepted-table projection not promoted](#2026-mississippi-absentee-product-authority-hold) |
| Current Ohio administrative context | [Separate registry-date-token channel, preserved county frames and complete replay](#2026-ohio-separate-current-registry-history-context) |
| Pending New York/Ohio qualification | [Real county access stops and held current-registry interpretation](#2026-new-york-access-stops-and-ohio-registry-history-qualification) |
| Current Oklahoma/Texas native counts | [77 in-person-early counties, two counted-ballot additions and complete fact-only replays](#2026-oklahoma-early-ballots-and-texas-counted-ballot-additions) |
| Published NC/OR successor packets | [Native revisions, unchanged probabilities and complete count/model replays](#2026-north-carolina-and-oregon-native-successor-packets) |
| Published Jefferson reference packet | [529 literal reference joins, 117 explicit holds and complete geometry/replay](#2026-jefferson-kentucky-partial-lojic-reference) |
| Current Jefferson Kentucky native facts | [268,257 Ballots Cast, 646 literal reporting labels and complete fact-only replay](#2026-jefferson-kentucky-native-participation-statistics) |
| Current AP/CHEP predictor-block evidence | [Complete exploratory source-response comparison and timing erratum; no model promotion](#exploratory-apchep-source-predictor-block-comparison) |
| Current Louisiana native group map | [Early/absentee report compositions, qualified parish context and complete fact-only reproduction](#2026-louisiana-native-earlyabsentee-group-map-and-data) |
| Current historical integer-format reconciliation | [179 qualified PA/UT native cells; original flags and all fractional/unknown holds retained](#historical-native-integer-format-reconciliation) |
| Current historical administrative cells | [Source-separated 2018/2020 observations, all51 state/year decisions and complete reproduction](#historical-native-administrative-cells-2018-and-2020) |
| Current Marion Iowa snapshot | [Unofficial General Election Total Ballots, contextual registration and retained source modes](#2026-marion-iowa-native-general-election-snapshot) |
| Current regional counts and map bindings | [Seven-state successors, full numerical packages and retained model-frame holds](#2026-regional-native-counts-and-new-mexico-map-bindings) |
| Current SC/AL administrative counts | [South Carolina state-only participation and Alabama corrected all-mode source selections](#2026-south-carolina-and-alabama-native-source-counts) |
| Current House-model disclosures | [Same-group variant sensitivity, exact versions and conditioned totals](#current-house-model-disclosures-and-variant-sensitivity) |
| Current Texas county expansion | [Eight direct counted-ballot additions, native discrepancies and typed source dates](#2026-texas-eight-native-county-reconciliations) |
| Current Missouri native additions | [Boone/Cole Ballots Cast, Cole reporting rows and explicitly reviewed county context](#2026-missouri-boone-and-cole-native-statistics) |
| Current King County native refresh | [935,956 printed Ballots Cast; complete source controls and unchanged county context](#2026-king-county-native-ballots-cast-successor) |
| Current Wayne County native evidence | [770 reporting units, a derived administrative composite, and reviewed county context](#2026-wayne-county-native-statistical-counts) |
| Current recorded-swing display | [All50 state values by default, with separate comparison holds](#recorded-house-swings-default-display-correction) |
| Current administrative subtotal refresh | [New Jersey: 15 same-measure successors and complete native queries](#2026-new-jersey-administrative-subtotal-successors) |
| Current state-reference/model refresh | [Oregon counted ballots, active registration and revision33](#2026-oregon-state-reference-and-registered-source-revision-33) |
| Current coherent count/model refresh | [North Carolina state/county counts, native group observations and revision32](#2026-coherent-north-carolina-counts-and-native-source-revision-32) |
| Current coherent native refresh | [Wyoming county/reporting counts and ballot-only model revision31](#2026-coherent-native-county-and-reporting-refresh-revision-31) |
| Current complete native context | [Revision30: complete reporting units, unchanged selected registration and modeled means](#2026-complete-native-source-context-revision-30) |
| Current registered-frame numerical revision | [Native revision29, unchanged Civic priors and preserved complete state queries](#2026-existing-registered-frame-model-native-control-revision-29) |
| Current county-primary access outcomes | [Independent originals, actual viewer resolution and retained stops](#2026-county-primary-originals-and-native-viewer-resolution) |
| Newer secondary county House comparison | [Complete all-unit queries, exact reference vectors and unresolved primary conflicts](#2026-newer-county-house-source-concordance) |
| Current native municipal refresh | [Vermont full turnout report, 247 municipal observations and explicit registration-frame review](#2026-vermont-native-turnout-report-and-municipal-refresh) |
| Current native county-count refresh | [Cape May same-measure successor, all51jurisdiction retention and live acceptance](#2026-native-cape-may-count-refresh) |
| New Jersey complete native tables | [All21county files, distinct administrative/contest frames and unresolved source conflicts](#2026-new-jersey-complete-native-pdf-measures) |
| Recorded-count display correction | [All50state raw totals remain inspectable independently of behavioral eligibility](#recorded-house-counts-versus-behavioral-eligibility) |
| Current combined-source priority | [2026 returns, NORC revisions and voter-poll reconciliation](#2026-combined-source-refresh-and-model-reconciliation) |
| Reusable participation updates | [Reviewed routine, complete queries and real no-op proof](#reviewed-routine-participation-batch) |
| Historical precinct bulk collection | [All-state source/query presence for 2016/2018/2020/2022/2024](#historical-precinct-bulk-collection-2016-through-2024) |
| House-result comparison correction | [Massachusetts and changed major-party contest coverage](#house-result-comparability-audit-and-correction) |
| Held reporting-row batch integration | [4,963 rows connected across Arkansas, Arizona and Wyoming](#held-reporting-rows-connected-to-county-navigation) |
| Current geographic gap integration | [Harris TX: counted ballots, not roster voters](#2026-harris-texas-held-counted-ballot-integration), [Jefferson WI: county ballots and native ward-group rows](#2026-jefferson-wisconsin-county-and-ward-group-participation) |
| Joint participation and House choices | [Four-axis source test: entry gains and drop-off negatives](#four-axis-administrative-participation-and-house-choice-dependence) |
| Fixed-marginal historical calibration | [Nested holdouts and six unvalidated current association stresses](#fixed-marginal-house-calibration-and-current-association-stresses) |
| Held-out cross-election dependence | [Paired heads and identical-margin flow test](#held-out-cross-election-dependence-and-identical-margin-flows) |
| Historical House panel evidence | [Conditional same-office source concordance, not population validation](#conditional-same-office-house-source-concordance) |
| Three House model families | [Same-source comparison; negative results retained](#three-fixed-norc-house-model-families) |
| Pennsylvania native control scope correction | [48 comparisons; no new counts or refit](#2026-pennsylvania-native-district-control-scope) |
| Official House endpoint successor | [47 qualified comparisons; unchanged NORC fits](#2026-official-house-endpoint-successor) |
| Alaska Senate internal source scopes | [Two native parents; no county or final-round promotion](#alaska-senate-two-native-parents-and-accounting-scopes) |
| NORC-informed demographic House transitions | [Learned associations, simulation and honest prediction checks](#2026-norc-informed-demographic-house-transitions) |
| Constraint-only flow bounds | [Aggregate-compatible gross flows](#2026-aggregate-compatible-gross-flow-bounds) |
| Atlas-wide swing model correction | [Both-endpoint return-constrained scenarios](#2026-both-endpoint-return-constrained-transition-scenarios) |
| Latest source-native 2026 group counts | [Louisiana early/absentee compositions](#2026-louisiana-source-native-early-group-counts-and-compositions) |
| Latest source-defined 2026 participation history | [Direct MEVP state/group profiles](#2026-mevp-direct-state-participant-history-and-experiences) |
| Latest deployed history view | [Separate 1996 adult/citizen points, alongside preserved later histories](#1996-cps-native-state-participation-and-response-frames) |
| Latest historical participation extension | [1996 native adult/citizen points and response frames](#1996-cps-native-state-participation-and-response-frames) |
| Latest blocked model test | [Demographic/geographic persistence: negative result](#demographic-and-geographic-adaptive-persistence-negative-result) |
| Latest missing-count integration | [Four Utah native county totals](#2026-utah-four-native-county-count-successors) |
| Historical demographic/state frames | [Every-state groups](#every-state-historical-demographic-participation), [CPS](#historical-cps-group-registration-and-response-frames), [EAC](#held-eac-historical-state-controls-complete-verified-publication) |
| Latest local integration | [Minnesota complete statistics](#2026-minnesota-complete-native-statistics), [Nevada county snapshots](#2026-nevada-distinct-county-participation-snapshots), [source-mode frame review](#2026-local-source-mode-frame-review), [Alabama county counts](#2026-alabama-native-county-ballots-cast), [earlier Minnesota follow-up](#2026-minnesota-native-county-and-precinct-follow-up), [four-city NH wards](#2026-native-ward-counts-in-four-new-hampshire-cities) |
| Administrative counts and registration | [Primary sources](#primary-administrative-data-and-population-denominators), [historical controls](#historical-administrative-participation-comparison), [Wyoming registers](#wyoming-declared-registration-reports-and-source-weighted-scenarios) |
| Local activity snapshots | [Direct MA city references](#2026-massachusetts-direct-city-precinct-references), [earlier MA counts](#2026-massachusetts-native-reporting-counts), [three-city NH wards](#2026-native-ward-counts-in-three-new-hampshire-cities), [earlier Manchester/Concord](#2026-native-ward-counts-in-manchester-and-concord), [earlier Manchester](#2026-manchester-native-ward-counts-on-current-municipal-context), [New Hampshire city sources](#2026-new-hampshire-four-city-sources-not-statecounty-or-precinct-turnout), [Illinois source-region context](#2026-illinois-source-region-activity-not-whole-county-totals), [Alaska geographic units](#2026-alaska-native-geographic-ballots-partial-app-reference), [Maine partial localities](#2026-project-maine-partial-locality-activity), [Connecticut towns](#2026-connecticut-native-town-counts-not-county-or-precinct-totals), [county provider frames](#2026-project-held-county-activity-frames), [Hawaii reporting areas](#2026-hawaii-four-election-administrations-five-census-county-decisions) |
| Candidate returns and context | [Historical compilations](#historical-returns-academic-and-publisher-compilations), [2026 counts](#current-2026-returns-exact-counts-and-comparison-products) |
| Survey definitions and current analyses | [Studies](#surveys-participation-histories-and-vote-choice-evidence), [derived outputs](#current-derived-analyses-and-remaining-reconciliation) |
| Collection rules and access holds | [Source classes](#status-and-source-classes), [access](#access-methodology-and-paidreference-only-leads), [automation](#automation-contract) |
| Website acceptance records | [Short Methods and GitHub docs](#website-methods-and-github-documentation), [source-backed navigation](#website-repair-source-backed-navigation-and-precinct-coverage) |

## Nationwide House display comparability correction

Website `93a8018683cd8fd319c8318104e27c3e5ca283fa` is actual-native and production
verified. The default map uses 33 supported directional comparisons; all 17
incompatible comparisons are neutral/hatched, regardless of sign. Raw arithmetic
is retained under **Raw source arithmetic - not a comparable swing**, in the
complete 50-state no-JS table and in every original full export. No source count,
sign, model fit or weight was repaired to obtain a preferred political direction.

An independent read-only audit passed 6,016 checks across 50 states, 435 districts,
1,401 candidates and all nine cases. It found no additional high-confidence source,
candidate-accounting, qualification or numerical defect. This scoped check is not
independent administrative outcome validation, source reacquisition or a guarantee
that every project gap is resolved.

[Complete audit and acceptance](data/participation-access/20261114-nationwide-swing-correction-01/acceptance.json),
[all 50 state findings](data/participation-access/20261114-nationwide-swing-correction-01/per-state-findings.json)
and [all 435 district findings](data/participation-access/20261114-nationwide-swing-correction-01/district-findings.json)
retain exact counts, comparison reasons and source clocks. Both actual viewport
checks cover all states, share/margin units, selection, model failure/recovery and
no-JavaScript. Both embedded numerical payloads, 213 saved rows, 3,341 link occurrences,
276 anchor occurrences and 436 complete downloads remain intact. The actual deployed
artifact is independently bound to its successful CI source and verified full bytes;
unrelated UK/congressional updates are separately source-pinned, not overwritten.
Automatic website/model delivery remains a separate unfinished implementation.

## 2026 automatic current-results intake

Source`d62ee2fb9d307d676c9513a3072c8f96149ba2c9` adds shared-Store-guarded
`scripts.results_intake`/`results_house`, an all51 registry and pinned complete
baseline. It preserves concurrent automatic snapshot`1bd8a926` unchanged.
The existing research workflow is replaced, not duplicated: hourly at minute23
through January31,2027 UTC, with manual dispatch. Actual GitHub run43606543817
at that exact source completed successfully on November14,2026 at14:46:28UTC.
Tests, collection, staged anonymous verification, activation and full artifact
14118555563 all succeeded. Local affected/shared tests:112 passed/two skips;
actual CI:35 passed/two optional-fixture skips.

The resulting version is
`99d3a448a80d581653766a079a95b32221289248e5f9152929c8e4cbd8e5eda4`,
staged commit`760eae86a900003930151f5bd158d5b24db3212f`, activated on the
independent `results-data` branch at`acb25c0ffd209914311fcdc182bedfdf8ad88e24`.
All12 full public bodies were anonymously downloaded and hash-verified.
The15,989,742-byte complete ZIP has SHA256
`95a514a8b18cb1cc5ab7ae59bff014365d33d99eb58d575bd1e8751e069b8927`;
its actual public download/extraction/literal replay reproduces all11 queries
without source requests. Complete facts, baseline shards, qualification queries,
processing code and tests are included, not metadata-only.

Coverage includes all51 jurisdiction dispositions and retained435 House
districts/1,401 candidate facts. The actual CI run successfully refreshed20
official directories plus the Oregon statistical feed. Oregon counts remain
1,992,463/3,109,123 active registrations; the source clock advanced without a
numerical change. The House declaration, provider capabilities and AL/NC/ND
statistical sources remain access-stopped. Their retained counts/clocks are not
fresh retrievals or evidence of certification. Existing143 exact access stops,
including race87098/87123/87495, survive fresh CI/cache state; no stopped source
was retried through another client, alias or old capability declaration.

The initial live run exposed string-valued accepted candidate counts; a strict
integer conversion and regression repaired projection without source changes.
The recovery reused permitted cached bodies and retained all new stops.
Independent source failures cannot erase other results; partial district sets
cannot yield falsely complete state sums. Newly declared unfamiliar layouts
remain explicit scope/parser-review items. This tool changes no website catalog,
geographic join, House behavioral gate, model fit or weight.

See [operation and replay](docs/RESULTS_INTAKE.md), [complete download](docs/DATA.md#automatic-current-results),
and [acceptance record](data/participation-access/20261114-automatic-results-01/acceptance.json).

## 2026 Tennessee and Montana partial native participation

The coherent count successor is live at website
`95e33a39efc115f722d071784eee59108bf57c8d`, catalog
`518ec40179094c4ee062cda0f2251d405d9e128d`, count version
`894d9a68adeb53269cce3517b517d80342403431a89e54172995785240e4286b`.
The `official` view denotes a primary administrative source, not certification.
These reports remain unofficial; filename/title wording does not override that.

Tennessee's Williamson report supplies105,105 Ballots Cast - Total and193,367
registered voters, printed54.36%. Native components are31,304 Election Day,
71,744 early,2,057 absentee and zero provisional. Its county clock is
11/03/2026 10:06PM; the reporting-row report is10:43PM, both with unknown
timezone. Preserve57 distinct printed statistics blocks versus the separate
58-unit reporting counter, seven unallocated ballots and11 registrations
between county and printed-row sums. Unit5-3 retains2,417 ballots/4,318
registrations and printed55.98%, while arithmetic rounds55.97%; its analytic
fraction remains null. Neither the difference nor a missing reporting row is
reconstructed. Coverage is one of95 counties, with94 native totals unknown.

Montana's Gallatin report supplies58,188 ballots/99,944 registered, printed
58.22%; Yellowstone supplies63,982 ballots with denominator, denominator
basis and fraction all unknown. Their separate native Election Summary
clocks are11/09/2026 07:03PM and04:42PM, respectively, timezone unknown.
Coverage is two of56 counties;54 native totals and the statewide total remain
unknown. No candidate-vote sum or inverted percentage fills a missing value.

Three complete immutable SDKs are necessary: original Tennessee
release445325984, repaired Montana445326040 and coherent combined445327488.
Each actual public ZIP was fully byte-verified, freshly extracted and executed:
15,24 and17 tests respectively, with54 exact count files each. Independent
source/typed/package reviews and fresh replay proofs are retained. Montana's
collector now fails closed before transport on newly discovered or malformed/
corrupt/unreadable/oversized stop ledgers. Original held packets and failed
proofs remain, not overwritten. See [complete downloads](docs/DATA.md#tennessee-and-montana-partial-native-participation).

Actual no-override desktop/phone acceptance checks302 prior provider values,
six native-county values,114 native reporting-row values and eight full source/
combined ZIP downloads. All51 interfaces/306 state-mode bindings, eight
current state references/6,450 early rows and Ohio's separate registry context
remain exact. Native artifact14116712517 has997,372,464 payload bytes and
999,966,720 raw tar bytes, both below the unchanged limit; all436 old
download pins remain. The nullable electorate basis no longer crashes the
renderer or invents a denominator, native codes are not called row ordinals,
and adjacent original-source/package links are separated.

All49 other state/DC shards, previous mode frames, current snapshot and native
reference remain unchanged. No new FIPS/geometry/cross-year match, precinct
map join, unique-person count or local demographic allocation is qualified.
All113 models, House endpoints, probabilities, fits and survey weights remain
unchanged: these partial county reports do not supply a compatible statewide
joint population frame. Exact new sources are retained in a versioned canonical
snapshot without replacing the independent legacy renderer, reader or tests.

## 2026 Kansas Greeley official source turnout

The Greeley County Clerk's official 2026 general-election declaration identifies
the exact retained workbook. The authority page is 10,080 bytes, SHA256
`bfd8a5115b2ef36a20a83a744f23f7bc16c6e251dd175cec0ca932474a6ad01b`;
the workbook is 7,942 bytes, SHA256
`7e7218dc2fa05cccf9cf03f8d0b38c9ca10958d40d3717a7af63c8e847156790`.
The source reports 451 voted plus nine counted provisionals, totaling 460,
with 853 registered voters and printed 53.93% turnout. Ten provisionals
submitted, nine counted and one not counted remain separate. Opaque MSD/GSD/HC
codes are not interpreted as voting methods. The unit is source-reported
voters in its turnout total, not generically relabeled ballots or independently
verified unique people. Registration is not an eligible-population estimate.

The declaration calls these official post-canvass results. No native count
clock or timezone is printed; November 13 server Last-Modified timestamps and
retrieval times are provenance only. Coverage is one of 105 Kansas counties;
104 native official county totals remain unknown, not zero. No statewide sum,
new FIPS/geometry join, precinct allocation or local demographic model follows.

Only the `official` view selects the new source row. All 105 older available,
early and mail county frames remain exact, including their separate provider
units and contextual maps. The unmatched native row is selector/table-only,
never substituted into a provider map. Other 50 state/DC shards, Ohio's separate
registry context and 24 original partitions, current snapshot and Kentucky
reference remain exact. No House endpoint, swing unit, model fit, probability
or weight changes; all 113 prior models and complete downloads remain.

Independent review held the first SDK because its collector could revisit
recorded stopped products and its stop narrative was misleading. The repair
removes those products from actionable collection, checks stops before
transport and correctly identifies the three original urllib 403 attempts as
stop-forming attempts. Original receipts, the first SDK and failed evidence
remain unchanged. The repair performed no network or real transport calls.
Independent source/data review and the narrow repair review pass; 14 tests
include five collector-stop guards. Two fresh worker executions, an independent
fresh extraction and actual public-download replay reproduce all 54 count files.

Immutable release 445279373 contains the complete 11,854,547-byte,
134-member SDK, SHA256
`85b1a93788c7aa0acade58348322641a71216b34264ae5f8e5b0011d4982013a`.
See [complete downloads](docs/DATA.md#kansas-greeley-official-source-turnout).
It includes complete permitted facts, numerical queries, all51 projections,
own code and tests, not publisher XLSX/HTML originals or private person data.
Python-process guards are not an OS sandbox; frozen creation-time planned
flags remain unchanged, with actual publication verification external.

Website `9ecc191e792fae20c65fee45de052eb657e10171` honors literal source
status instead of incorrectly labeling the official report unofficial, and
omits unsupported precinct-reporting text. Catalog
`d735fba69caf4e54e1e718e5e3b5a8451c4ef5e7` activates count version
`92092b9931902e5af08a3b78e177cd6c98035d26c99fa83c0ea577d1377aee95`.
Actual artifact 14113644559 has 997,372,160 payload bytes and 999,966,720 raw
tar bytes; all 436 old download pins remain exact. Actual no-override checks
cover all51 interfaces/306 bindings/eight state references/6,450 early rows,
210 retained Kansas provider county values, the official native observation
at both widths, mode/map exclusions and two complete SDK downloads. Ohio's
separate context also passes an actual desktop/phone regression. Exact three
owned sources are persisted without replacing the older independent renderer,
reader, tests, canonical HEADs or indexes.

## 2026 Mississippi absentee product authority hold

A privately retained 82-county absentee PDF supports an internally reconciled
83-unit, 498-cell projection, but the actual official declaration-to-exact-PDF
mapping is not retained. Intrinsic document text and a successful direct PDF
download do not establish that publication chain. Independent scientific/
typed and technical SDK reproduction checks pass; source authority and
publication remain HOLD. No observation, candidate, SDK or map was activated
or merged into Kansas. Do not treat this as all-method participation, mail-only
activity, unique people, turnout or staying home.

A separate private repair makes future shared-stop discovery fail-closed;
11 offline tests pass with zero new requests. It does not repair the missing
primary declaration. The original candidate, archive, actual stops and failed
evidence remain unchanged, and no replacement SDK was built. Stopped products
stay stopped across clients. Other genuinely independent primary products
remain possible; this bounded hold is not a statewide-unavailability claim.

## 2026 Ohio separate current-registry history context

The neutral Butler County aggregate is now live in a separate administrative
context channel, not a county ballot or turnout frame. Independent streaming
verification of the privately retained current voter-record CSV supports
148,569 current-registration records with at least one exactly parsed
11/03/2026 history-date token, within249,106 current records. Record identifiers
are unique within this file; this does not establish unique people. Only the
observed Active/Inactive frame is known; removed/cancelled-record treatment,
history completeness, election type and opaque method/party codes remain
unqualified. Missing history is not observed nonparticipation.

The actual Butler Election Vault index declares the normal POST download,
product name and file-update literal. The verified source CSV is133,021,454
bytes, SHA256
`0eac6dfcf5c03f26c0489ddd0b0434340db9450245077d9a8478cf5e95e7cee0`.
Its file update is **Saturday, November7,2026 4:02 AM**, timezone unknown,
not4:03 AM and not an election-result/completion clock. The distributed row
is a derived public aggregate from privately retained person-record input,
not a publisher-supplied aggregate. Individual rows, identifiers, contacts,
birth dates, histories and rare private diagnostics are excluded.

Only `views.available.administrative_contexts` selects the new record.
All24 original Ohio geographic/nongeographic/hold lists across six modes
remain exact, including88 available county rows and88 each in early/mail.
Official/UF frames stay empty. The optional typed role rejects ballot-frame
aliases, geographic joins and denominator/rate promotion. A separate selector,
source-unit card and explicit table action never enter county-map selection;
the table selection survives asynchronous map rendering. The ordinary source
detail also honors its supplied measure label rather than inventing ballots.

Immutable release445249918 contains the complete132-member SDK03,
16,209,212 bytes, SHA256
`9c79a7ea43f0501b2c17d3e909165b55954bf3c7523309d3048a229ced238cc3`.
See [complete downloads](docs/DATA.md#ohio-separate-current-registry-history-context).
Independent source/typed/SDK review, two fresh extractions and an actual
public-download replay pass9 tests, five process-local API guards and54 exact
count outputs. Replay starts from complete accepted aggregate facts; it does
not re-extract private records or claim an OS sandbox. SDK02 remains a prior
immutable scientific archive but its geographic-slot candidate was never
activated; the original ballot-worded candidate remains wholly held.

Website `fd14b2a4783abc32a1208a2e12a637a14a3d7aaf` and catalog
`7e0f44afe854512937553fe9047be1af0da50533` activate count version
`afe46ca7eb431e602a5504870250931c91fd69675192d503779f81022f6f9c4a`.
Actual native artifact14112792252 has997,371,977 payload bytes and999,966,720
raw tar bytes, both below1 GB; all436 old download pins remain exact.
No-override production passes all51 interfaces/306 mode bindings, unchanged
eight state references/6,450 early rows,176 ordinary Ohio county values,
desktop/phone context/mode/map exclusions and two actual full SDK downloads.
Initial cached old-version loads were not accepted; final checks assert the
actual browser module's new version. Exact four publication sources are
persisted separately from the preserved older independent local renderer/tests.

All other50 shards, current snapshot, Kentucky reference and other catalog
entries are unchanged, including Oklahoma233 records and Texas13 native
counties. No House endpoint, swing unit, model fit, probability, weight or
conditional transition estimate changes. Ohio's genuine full-election
participation gap and broader nationwide source/model work remain open.

## 2026 New York access stops and Ohio registry-history qualification

The bounded New York follow-up received actual HTTP403 from five official
county routes: Monroe elections home and results, Saratoga Board of Elections,
Seneca Board of Elections, and Schenectady elections. Exact STOP receipts and
the five-test baseline/hold verification are retained privately. Earlier NY
HomeNoJS and November1 registration-workbook stops remain binding. No declared
numerical original was acquired or promoted, no candidate/SDK was published,
and the full51 accepted projection is unchanged. Search-discovered product
links and snippets were not treated as source-authority evidence or counts.
Other genuinely independent primary products remain a possible route; these
outcomes are not proof of statewide unavailability.

The original ballot-worded Ohio candidate remains withheld; the separate
neutral context above does not promote its stronger claims. Its Butler County Election Vault
index supports the publisher, normal POST download declaration, product name
and file-update literal. The underlying current voter-record CSV and receipt
were located in the already-held private linked-history source collection.
Independent streaming verification supports the neutral current-record
date-token predicate, not the stronger ballot/election-type claims. The source
is person-record input, not a
publisher-supplied public aggregate; any distributable result must identify
its derived aggregate nature without exposing individual records or histories.

The referenced directive hash points to a derived evidence record rather than
retained directive bytes. The separately claimed ballot-total context likewise
lacks retained primary support. Date-coded history flags alone therefore do
not establish counted-ballot, general-election or complete all-method semantics.
Observed Active/Inactive status values do not establish how removed/cancelled
registrants are treated. A file-update clock is not an election-result clock,
and one current record carrying a matching token is not necessarily a unique
history credit or a complete unique participant.

That original private package's mechanical CRC/manifest/portable-replay checks
and individual-record exclusion passed independent review, but its stronger
source meaning, typed units and publication remain HOLD. Its count/model
projection was not activated. The later neutral channel resolves only the
administrative-context display, not counted-ballot or complete-election source
qualification. Do not repair discrepancies by merging different measures.

## 2026 Oklahoma early ballots and Texas counted-ballot additions

The complete immutable fact-only SDKs are releases445204294 (Oklahoma) and
445206337 (Texas), with exact pins and commands in
[complete downloads](docs/DATA.md#oklahoma-early-ballots-and-texas-counted-ballot-additions).
Each contains complete accepted all51 numerical projections, source facts,
queries, compiler, tests and54 reproduced count files. Public replay starts
from accepted sufficient factual inputs, not excluded publisher PDF/HTML
extraction. Every archive member and106 decompressed GZIP bodies were checked
for private paths/session markers; neither package contains publisher media,
templates, nested archives, private respondents, predictions or estimators.
ZIP member locations are inventories, not phantom standalone release assets.

The official Oklahoma absentee-statistics index declares the October31,2026
in-person absentee report. All78 pages were independently parsed twice with
exact agreement. Its186,488 ballots reconcile across77 counties and the state
parent; the printed8:34 PM clock has no supplied timezone. Republican89,779,
Democrat71,679, Libertarian780 and Independent24,250 are administrative party
affiliations, not vote choices. Of312 affiliation query cells,298 are printed
and14 omitted Libertarian cells are uniquely forced to zero by nonnegative
exhaustive accounting; four zeros are explicitly printed. Including the78
printed totals, all390 query cells remain downloadable with provenance.

Only the77 county observations enter the `in_person_early` view; the state
parent is unselected reconciliation evidence. All155 older Oklahoma records,
the distinct mail view, current snapshot and other50 jurisdiction shards stay
exact. The results portal's actual403 remains stopped. No full-election
turnout, registration denominator, rate, unique-person, precinct or map
qualification follows from this early report.

Actual official Uvalde and Caldwell county result indexes independently
declare the exact retained reconciliation PDFs. Their body pins and exact
index-to-PDF mappings are preserved. Uvalde's printed counted total is8,545;
Caldwell's is14,932. All42 source facts retain received/counted stages,
registered-voter context, rejected/pending/outstanding measures and source
discrepancies. Uvalde's92 rejected/pending provisionals are not its94 estimated
provisionals. Differences1 and8 are not repaired. Native signer dates11/3/26
and11/3/2026 are attestation provenance, never count-update clocks/timezones.
The reviewed Census county identities are derived, not FIPS printed on forms.

Texas native county coverage increases11 ->13 of254;241 remain unknown.
Both additions remain preliminary/unofficial and rate/geometry holds remain.
All1,029 older Texas records, all233 corrected Oklahoma records and all other
shards are preserved; counted totals do not enter early/mail frames.
The combined count version459c853f was atomically activated at cataloge3a42628,
with both compiled source projections retained at immutable stagee188012a.
The later separate Ohio context preserves this complete Oklahoma/Texas delta.
All other catalog entries, Kentucky's loaded preimage and the full current
snapshot are exact. No House endpoint, model, prior, weight or transition
probability was changed.

Independent source/data/typed/SDK reviews pass. Each SDK has two fresh
extracted replays and actual public-download execution: Oklahoma8 tests/four
Python API guards; Texas9 tests/six guards;54 outputs each. They claim
process-local controls, not an OS sandbox. Whole existing-page previews and
actual no-override desktop/mobile production check308 Oklahoma county-mode
values and52 Texas native county-mode values, separate source modes, scope
holds and all full SDK downloads. Common acceptance preserves all51
interfaces/306 bindings/eight state references/6,450 early rows.

Website source0c6f2be clarifies missing statewide totals versus actual local
reports and clears stale error text after a healthy load. No statewide sum is
synthesized. Its actual artifact14108859409 is997,366,958 payload bytes and
999,966,720 tar bytes; all436 old complete download pins remain. Unrelated UK
generated-time/run-id fields account exactly for35 provenance-only artifact
differences; every other unaffected byte is retained. The independent older
canonical renderer remains untouched, with the exact two new published
sources retained separately. Broader all-state/model gaps and the later full
audit/beautification remain open.

## 2026 North Carolina and Oregon native successor packets

The complete count and model SDKs are public and immutable:
releases445143216 and445143258, respectively. Their exact pins and offline
commands are in [complete downloads](docs/DATA.md#north-carolina-and-oregon-native-successors).
Permitted original NC aggregate products remain included; publisher HTML/PDF/
application templates and private respondents/predictions/estimators are excluded.
Both fresh extracted replays and actual anonymous public-download executions pass:
115 count tests/54 exact count files;19 model tests/25 exact revision34 and25
exact revision35 outputs. All51 baseline jurisdiction shards remain available.

The accepted selected NC reference changes4,243,180 ->4,242,662 (-518), with
7,885,046 active-plus-inactive registrations unchanged. The73 changed county rows
plus the statewide parent are74 changed observations; all100 county sums
reconcile. County source titles are OFFICIAL except HALIFAX; the statewide title
remains UNOFFICIAL. Do not substitute the raw crawler's -2 comparison for this
accepted-reference difference. Oregon changes2,019,444/3,109,145 ->
1,992,463/3,109,123 (-26,981 ballots/-22 active registrations); the native PT
clock remains literal, not a newly inferred IANA timezone.

Study probabilities, weights and fitted models are unchanged. NC conditional
means do not change. Oregon conditional participant/complement source units
change by -14.741656589460355407.../-7.258343410539644593..., mechanically
partitioning the -22 registration-unit revision, not observed staying home.
Native-minus-model differences remain nominal diagnostics, not validated errors.
The website's strict two-row overlay retains its later New Mexico revision34,
other49 jurisdiction decisions and other32 conditional scenarios. Both actual
count/model publication receipts must verify before ready download links render.
Member fragments are inventories inside full ZIPs, not standalone HTTP assets.

Website runtime source2d2d2c504cac896722145796bb335942acc7a640 is live; its
non-runtime acceptance-checker follow-up isef92704fb68fe67f7cbe9d8f242ee28af99978b2.
Catalog3e0e37b8635747f2c8dfe953478f52ce0924b084 atomically activates counts
`7afe2ba0db377e8d5a81c8b82c0b124834f3b8b6c3cf1c48181c9e5e3a4bb8c7`
and native reference
`7e017f32899244774b175d7c96c77a25e53aa7bfaff1dba52c55c1a81f76d7a9`,
after90 staged anonymous file checks. Actual native artifact14106597734 from
successful workflow43577480552 has997,366,767-byte payload/999,966,720-byte
tar; actual served page/scripts and all436 old complete download pins match.
No-override production passes all51 jurisdiction interfaces/306 count bindings,
the exact eight-report/6,450-early-row snapshot and desktop/phone county/source
checks. Civic desktop/mobile/no-JavaScript/failed-JSON cases verify all79 study
rows,112 flow rows,34 conditional scenarios,51 decisions and real ZIP members.
No new House endpoint, family, weight, individual transition identification or
county/precinct demographic allocation is claimed.

## 2026 Jefferson Kentucky partial LOJIC reference

Immutable release445140564 publishes the complete permitted bare geometry,
accepted numerical observations, all seven factual queries/dispositions,
unchanged prior native bodies, compiler/reader tests and exact offline replay.
The75-member SDK is41,769,394 bytes, SHA256
`b76a5bab5d337c85052721bd17d5b4e81fc6cec265c447ff149236c489945eb7`.
Two fresh extracted replays and an actual anonymous public-download replay each
pass8 Python/10 Node tests and reproduce7 factual plus36 runtime outputs exactly.
All31 prior non-index native bodies remain byte-identical.

The source-declared LOJIC public-authoritative item is
`b82cf258640843cabe1d234a5d4472ec`; published Hub PDDL terms qualify bare dataset
geometry, not publisher PDF/HTML/rendered maps/application templates. All current
count, identity, native-coordinate and source-server WGS84 queries contain646
unique identities. Preserve the older service-description623/2013 versus
authoritative-item2020 conflict. Geometry retrieval on November14,2026 and the
companion map's printed November7 date are distinct; neither certifies legal
November3 election boundaries.

Only529 exact-literal joins map. The117 held labels comprise60 suffixed labels,
invalid K161, six conservative invalid-bbox neighbors and50 other overlap labels.
No suffix is stripped, invalid polygon repaired or overlap clipped. All646
native unit counts/19 true zeros remain available, including18 mapped zeros;
unmapped is not zero. The separate `participation.reference_bindings.v1`
contract pins the actual KY count shard and preserves the complete original
observation, without claiming the foundational legacy review approved this join.
Rates, registered/eligible denominators, unique people and local demographic/
behavioral allocations remain unqualified. Source/runtime/SDK reviews pass;
whole existing-page private desktop/phone checks pass1058 count/shade/ARIA
comparisons, all source labels, mode holds, genuine keyboard selection, two
actual full public ZIP downloads and six explicit failure/retry/race cases.
The same1058 map/count/shade/ARIA checks, all646 source labels, mode holds,
physical keyboard changes and two full public SDK downloads pass true
no-override desktop/phone production after joint catalog activation. Full source
and geometry qualification does not resolve the local population/model-frame gap.

## 2026 Jefferson Kentucky native participation statistics

The county clerk's declared November3,2026 General Election reports supply
268,257 native **Ballots Cast - Total**: Election Day187,470, Mail8,942,
Walk-in Excuse1,309, Walk-in Early70,532 and Provisional4. These are cast
ballots, not candidate selections, unique people or returned-mail envelopes.
The county parent and646 native reporting labels are alternative views, not
additive populations. All60 suffix labels and19 true-zero TOTAL units remain.

The complete query contains7,758 statistical numeric cells,4,819 literal zeros,
647 SOVC participation rows including its separate parent, all5,365 source-page
decisions and652 exact-zero cross-report comparisons. Reports share publisher
lineage; agreement is not independent replication. The summary clock is
`11/04/2026     3:07 PM`, SOVC `11/05/2026 02:44PM`, and precinct report
`11/06/2026     9:52 AM`. Printed zones are unknown; PDF creation offsets do
not supply them. The summary/precinct status literal is `UNOFFICIAL RESULTS`;
this status is not transferred onto SOVC. Native646/646 reporting is not
certification, finality or a common-as-of claim across reports.

The summary has no native blank-ballot measure. The precinct blank TOTAL sum19
is derived, not a printed county statistic. Registration, analysis turnout
rates, FIPS/precinct-boundary joins and individual transitions remain withheld.
Native counts, clock mirrors, literal unit labels and reviewed qualifications
are separately bound. The first typed/UI candidate was held and repaired after
critique; its count values were not repaired or changed.

The immutable fact-only SDK445091351 is13,649,216 bytes/150 members with full
authenticated and anonymous verification. Two fresh extracted executions and
the actual public-download replay each pass28 tests/four selected Python API
guard probes and reproduce all54 candidate counts outputs. All483 prior KY
records, early/mail selections and the other50 state shards remain exact.
The public replay starts from complete reviewed facts; publisher PDFs, HTML,
images and templates are excluded. It does not re-extract those originals or
reproduce the unchanged native geometry/model products.
The shared compiler is unchanged. Source3fe2cad and atomic catalogbf3599bf
deliver counts49aca906 without a new website build. Actual no-override production
at1440/390 checks all1,292 unit/value combinations and two complete SDK downloads;
separate early/mail provider counts71861/7304 remain unchanged. The actual33
served bodies and436 prior download pins match the accepted native artifact.
Ten canonical extractor tests pass, with deliberately old canonical HEADs and
indexes preserved. The189-file concurrent automatic snapshoted6130a is retained.
Final source/native/runtime/package acceptance records remain separate from
population/model qualification; all other models and weights are unchanged.
[Complete download and command](docs/DATA.md#jefferson-kentucky-native-ballots-and-reporting-labels).

## Exploratory AP/CHEP source predictor-block comparison

The new source-only comparison evaluates12 fixed specifications:10 multinomial
logistic fits and two training-weighted marginal baselines. Historical AP2022
to AP2024 scoring uses the common48-state poll-close-weight frame, excluding
DE/WV from both training and scoring. CHEP2026 uses one pooled respondent
holdout drawn from its50 observed survey states; this does not establish
state-inference qualification or support D.C.

Vocabulary and regularization-weight normalization use training rows only.
Native prior-choice routing, party-code reversal, Other, unknown and modeled
nonvote classes remain distinct. Current2026 returns never enter features or
selection. This is source-response prediction, not observed staying home or
independent population validation; CHEP weight calibration remains a limitation.

The small AP age/education change is log loss0.738564877355 to0.735829569640
and Brier0.357106096317 to0.356447395408. Adding state improves CHEP's
respondent score but worsens AP transfer. Sex/RUCC slightly improves CHEP log
loss while worsening Brier. All evaluations and calibration queries remain,
not only favorable results. AP's one-prior and CHEP's two-prior specifications
are thematic counterparts, not the same identified mechanism. No uncertainty
analysis or new independent historical episode establishes generalization.

Independent critique caught an impossible original protocol freeze timestamp.
The pinned erratum withdraws the prefit-freeze claim; the comparison is
explicitly exploratory/post hoc on seen source outcomes. Original artifacts
remain labeled forensic evidence, not silently retimestamped. The arithmetic
follow-up comparison is against `prior_only`, not the accepted richer model;
no state estimate, live default, model/weight or House gate is promoted.

Immutable445071249 provides the complete55,826-byte/27-member numerical SDK,
SHA256 `9532f991077027fbcca7396c17ac03cb129e8d93ce1988c7ad98d00207f36b37`.
It contains all coarse numerical facts,12 evaluations,102 jurisdiction-study
decisions covering all51 jurisdictions, calibration queries, code, tests,
observed dependencies and erratum.
Two fresh extracted replays reproduce all six core outputs. A genuinely
downloaded public SDK replay plus15 dependency and six standard-library tests
also pass. Selected Python APIs are intercepted/probed; OS-level containment
is not claimed. Aggregate replay does not repeat private source fits.
No respondents, predictions, fine cells, state scores or estimators are exported.
[Methods and errors](docs/NORC_HOUSE_TRANSITIONS.md#source-predictor-blocks-exploratory-apchep-comparison)
and [complete reproduction](docs/DATA.md#exploratory-apchep-predictor-block-comparison).

## 2026 Louisiana native early/absentee group map and data

Scientific source `7bffd4d33b2ca32fbb613f419707b593ce93f86b` and website
source `0ef8ef35ce2dcc9298d4fbbd0d238b4bc560dbb7` add a source-bound Louisiana
reader. Dataset `source-native-la-early-group-data`, version `5e58886f`, is a
separate entry in catalog `9e6d7625`; all previous entries remain exact.
It preserves1,040 native cells,65 profiles,455 group compositions,448 parish/
group bindings,128 provider diagnostics and all51 source-scope decisions.
Only Louisiana is supported by this source; other states are not zeros.

The November3,2026 native early/absentee report has VOTES536,190:
INPER448,588 and ABS87,602. Native race margins are WHITE328,590,
BLACK184,348 and OTHER23,252; sex margins are MALE224,376 and FEMALE311,536.
The278 state sex arithmetic residual,37 parish residuals and21 literal zero
cells remain. Shares use each profile's own native VOTES, not a population,
registration or classified-sex denominator. The state parent and parish/
demographic margins are controls, not additive independent populations.

This is not full-election turnout, a count of unique people, or identified
switching/nonparticipation/entry. Native ABS is not promoted to mail returned;
party accounting is not vote choice. Race/sex/method margins are not joint
groups or aliases for CPS/NORC categories. No fitted mean, weight or House
comparison gate changes. Source codes01-64 are not FIPS. The64 reviewed parish
context shapes are not2026 voting precincts; upstream lineage is not established.
Printed11/10/2026 3:10:06 AM has unknown timezone. The1900-01-01 through
2026-11-09 query filter is not an observed voting period or a finality claim.

Immutable445047387/asset746448557 contains the complete5,650,023-byte/39-member
fact-only SDK, SHA256 `627d791dc160c5609f92baac5491a74fd807e7114c7c29477e5d2d113168ae04`.
All permitted aggregate inputs, geometry, complete queries, code, tests and
outputs are included; the original publisher PDF/application and private
respondents are not. Three offline replays run six portable tests and four
network/DNS/child denial probes, reproducing15 outputs and the16-file tree.
Accepted full query artifacts are verified/copied replay inputs; the typed
projection is recomputed. No re-OCR or new source acquisition is claimed.
[Complete download and commands](docs/DATA.md#louisiana-native-earlyabsentee-group-compositions).

Actual no-override1440/390 production checks pass all1,792 count/share/color/
accessibility-label renderings, physical parish selection, Enter/Space,
lazy/scope behavior and both complete SDK hashes. Six separate explicit
503/checksum/delayed-response tests preserve verified downloads, substitute no
values and retry correctly. Actual artifact14101237393 from Pages43563002467
has997,358,400 payload/999,956,480 tar bytes, both below1e9. All33 served
bodies,436 prior download pins,113 original entries and115 actual archived/
linked bodies verify. Canonical29 reader and six research tests pass, retaining
the older renderer and protected HEADs/indexes.
[Actual acceptance](data/participation-access/20261114-louisiana-native-groups-01/website-acceptance.json).

## Historical native integer-format reconciliation

Scientific source `29ec90582cde8134ac904949fae88bafd95d1a60` corrects one
mechanical parser hold, not a publisher suppression or a new source snapshot.
The earlier generic classifier accepted only an optional minus sign followed
by digits. It therefore labeled native `1,054`-style values
`noninteger_native_literal`, even though the complete native field is an
unambiguous comma-grouped integer.

Exactly179 administrative source cells are newly qualified: Pennsylvania163
and Utah16, from the already-held2018/2020 General Election precinct files.
The bridge accepts only that generated flag plus proper ASCII thousands
grouping and an optional all-zero decimal suffix. It still independently
matches native office/value, exact election/source identity and safe integer
bounds. The original literal, native fields, qualifications and
`upstream_source_status` remain. Unknown, suppressed, malformed-grouping and
actual fractional values are not promoted or rounded.

All121,661 source-cell identities and39 snapshots remain;16 other state shards
are byte-identical. Reported zeros remain12,837; unknowns remain115;305 actual
fractional holds remain. There are still18 jurisdictions with observations and
all102 state/year decisions, not universal historical precinct turnout.
These179 cells are not179 newly identified people or an additive participant
total. There is no new rate, denominator, boundary join, cross-year identity,
2026 observation, weight or behavioral fit.

The complete554,009,197-byte standalone successor has SHA256
`2d5961cef2a4e4c44d479eb686aea9e941f93dbd41f6220edec47484637d1b05`.
All three full factual inputs, exact code, ten tests, all20 numerical outputs
and the complete179-cell before/after source query are included. Both fresh
replays and a genuinely extracted download execute the literal
`sh -eu REPRODUCE.txt`, with six network/DNS/child-denial probes and every output
byte-exact. The source/data and full package are independently reviewed.
[Complete successor](docs/DATA.md#historical-native-integer-format-successor).

History version `a8e917a7` supersedes `88d51667` only in this reviewed source-
format qualification. The earlier package remains immutable and reproducible;
its original484 holds are not silently rewritten. Current2026 counts `900c675c`,
native `b591e846`, fitted means, priors, weights, endpoints and33/17 House
qualification remain unchanged.

The successor is immutable **445021938**, asset746326173, with authenticated
and anonymous full-body verification. Catalog
`6f5c68a9b8d76f5bf599cbca34fdce92f55a16a7` activates the independently verified
20-file version; only `states/PA.json.gz` and `states/UT.json.gz` change.
Actual no-override1440/390 acceptance renders every affected source cell:
358 exact count/native-field checks, plus both full554,009,197-byte ZIP hashes.
Ten canonical tests pass. No site rebuild was needed: all32 current live
bodies and the publication manifest remain byte-exact to accepted artifact
14098410480, whose997,339,994 payload/999,936,000 tar bytes remain below1e9.
The prior actual115-body/436-download/113-original preservation proof is reused
for that unchanged native delivery, not claimed as a new build.
[Complete actual acceptance](data/participation-access/20261114-historical-native-integer-01/website-acceptance.json).

## Historical native administrative cells: 2018 and 2020

Original accepted delivery, retained by the integer-format successor above.

Scientific source `8d4e6ea5ce6ff1f1cee821b9ec8b4654e91276e1` projects only
explicit native Ballots Cast and registration-stock cells from three already
verified, complete official-workbook/OpenElections factual components.
There are121,661 separate source cells in39 snapshots across18 jurisdictions,
including12,837 reported zeros,115 unknowns and484 withheld/noninteger cells.
All51 jurisdictions have explicit decisions for2018 and2020:102 decisions,
not a claim that all51 have qualified administrative observations.
Other years are not classified as missing merely because this projection
does not evaluate them.

Alternative official/OpenElections copies, totals, ballot styles and modes
remain separate. Cells are not unique people or a safely additive precinct
total; native county/unit/category fields are retained literally. Candidate
votes do not substitute for participation. Registration is not automatically
a turnout denominator, and no rate, demographic allocation, boundary join or
cross-year precinct identity is approved.

Immutable release **445000489** provides the complete553,681,587-byte package,
SHA256 `e052b3e1069c99ca8df04e7d0d20c49b86f404adfa9582b86b299b0da0307ca1`.
It contains all three full input components, exact producing code/tests,
every numerical output and every decision. Authenticated-draft and anonymous
public full-body hashes agree. Two fresh extracted downloads execute the
literal `sh -eu REPRODUCE.txt` with `python3`, eight tests, six network/DNS/
child-denial probes and all20 output files byte-exact. Original publisher
templates and private respondents are not added.
[Complete download and reproduction](docs/DATA.md#historical-native-source-cells-and-marion-iowa).

Dataset `participation-historical-native-counts`, version `88d51667`, is an
independent catalog entry. It does not replace demographic turnout histories,
current2026 counts, source-native map bindings or behavioral model inputs.
Catalog `ac0293a616f7621d84c53bde4f57e2544ea024b2` retains all other entries.
The existing-site historical panel separates source snapshot, native county
field, measure and unit/category search, pages100 rows and exposes original
native fields plus the complete state and scientific downloads. Unsupported
states are not displayed as zero; the panel is unavailable outside2018/2020.

Website `ea329b33` passes both source guards and actual Pages43554754547.
Artifact14098410480 has997,339,994 payload/999,936,000 tar bytes, both below1e9.
All32 served bodies,436 prior download pins,113 original publication entries
and115 actual archived/linked asset bodies are verified. No-override1440/390
tests validate all121,661 historical cells and all51 current jurisdictions,
actual filters/paging/native fields, distinct zero/unknown/withheld cells,
and both complete download hashes. Four separately labeled503/checksum fault
cases retain the verified complete package and successfully retry the real body.
Canonical23 reader tests pass; the older renderer receives only its seven
state-setter paths and historical hooks, preserving every unrelated byte,
both canonical HEADs/indexes and only three owned manifest script keys.
[Actual acceptance](data/participation-access/20261114-historical-native-and-ia-01/website-acceptance.json).

## 2026 Marion Iowa native General Election snapshot

The already-held Marion County source is a November3 **General Election**
report, explicitly **UNOFFICIAL**, with native date/time
`11/3/2026 9:34:08 PM CST`. All nine repeated statistical headers independently
agree on **16,373 Total Ballots**,25,041 registered voters and one blank ballot.
Nineteen of19 precincts reporting does not establish certification or finality.
All144 header query cells are preserved; the repeated headers are not nine
independent observations to add.

One new county observation raises Iowa's direct all-method county coverage
from1/99 to2/99. All399 prior Iowa observations and their early/returned modes,
the other50 state shards, the current model snapshot and native `b591e846`
remain exact. The contextual registration stock and native printed fraction
do not qualify an analytical denominator or turnout rate. Unique people,
Iowa native map bindings, state totals, weights and demographic/behavioral
fits are not inferred.

The repaired fact-only package is immutable **445000488**:
41,721,387 bytes/SHA256
`13ff277c51c546901fc34af5e19e47b9fd10b01848e3b410a6767f461adf0869`.
It includes complete51-jurisdiction sufficient baselines, all144 header facts/
queries, producing code, ten runnable tests and exact offline reproduction.
Both fresh replays and a genuinely extracted download reproduce59 outputs.
Public replay starts from reviewed permitted facts, not a false claim to
re-OCR the excluded publisher PDF. The original source SHA256 remains
`4627272fdf72d35b2c0d1a20b715efce5242d042ae5e00242cd7242f8d0ae002`.
[Complete download](docs/DATA.md#historical-native-source-cells-and-marion-iowa).

Counts `900c675c` were verified at54 anonymous immutable paths and activated
in catalog `59e1c99c`; the subsequent historical entry `ac0293a6` preserves
them. The source/data and repaired package each received independent critique.
The earlier private PDF-containing/placeholder packet and its first
non-runnable tests were not published; their failed evidence is retained.
Texas's recorded+11.97610548 Democratic two-party-share points, all33 qualified/
17 held behavioral comparisons and the existing fitted means/weights remain
unchanged. This is a new administrative observation, not newly identified
switching, first-ever voting or staying home.

## 2026 regional native counts and New Mexico map bindings

Earlier accepted regional delivery, retained by the historical/Marion successor
above; its immutable packages and source-specific qualifications remain valid.

The shared routine's source `8c422c9` and immutable release **444945203**,
`participation-native-regional-merge-20261113-03`, retain complete permitted
inputs, code, tests, every query and all withholding decisions. Both new assets
have authenticated-draft and anonymous-public full-body verification. Five older
immutable releases and all93 dependency assets retain their exact IDs, sizes,
digests and URLs; unchanged dependencies were not uploaded again.
[Complete packages and reproduction](docs/DATA.md#current-regional-native-counts-and-map-bindings).

Counts `b21e7c22` and native bindings `b591e846` were activated together in
catalog `b2d439b7360ad3e301d885779559776281ae6b12`, after87 anonymous immutable
file checks. All51 jurisdictions remain; the other44 state shards, including
the accepted SC/AL and corrected IN/KS selections, are byte-identical.

| State | Qualified change and limits |
|---|---|
| CA | Native county aggregate12,898,770; the native measure is not automatically unique voters, counted ballots or a qualified model control |
| MI |80 selected county QVF activity observations; all83 source rows retained; not tabulator ballots or deduplicated people; Bay/Isabella/Wayne alternative totals held |
| MO | Platte County45,223; original counting scope, unknown analytical denominator and source clock retained |
| NE | State767,046;144 new selected reporting units sum511,037; the256,009 difference is not an accounting closure or inferred missing voters |
| NM | State731,491 with source registration1,469,718; existing2,177 shapes now carry1,208 bound counts and969 unknowns; six analytical rates remain held |
| TX | Tarrant734,929 and Bexar672,231 counted ballots; coverage11/254 counties, with243 unknown rather than zero |
| WI | Walworth46,612, Oconto18,982 and Dunn19,896;67 additional source reporting rows remain table-only, not invented precinct geography |

The Nebraska state and reporting frames are not additive or complete against
each other. Its source registration1,265,162 differs from the model's1,265,022;
the140 difference does not establish a compatible cutoff/status bridge.
NE and CA model-control changes remain held. New Mexico's separately reviewed
native-reference revision34 is already live and persistent: the qualified
731,209-to731,491 numerator/clock/diagnostic update preserves registration,
priors, fitted means, probabilities and weights. This regional delivery adds
no further fit or behavioral change. Hancock IN and all five Harvey KS facts
remain source-detail-only, not duplicate selected counties.

The display-compatibility repair fills missing metadata on1,487 rows, including
complete factual-package links for216 new and1,271 retained Nebraska rows.
Its71 electorate labels explicitly say the analytical denominator is withheld
or not supplied; no denominator value, rate, native clock, geometry, existing
nonnull source link or source fact is changed by that repair. A separate generic
renderer fix exposes supplied complete packages on legacy rows without adding
fake review IDs. All430 actual MO/WI/NE detail/link checks pass at both widths.

The first broad live test caught a missing coverage-panel link after its
numerical and New Mexico polygon checks; that failure is retained, not waived.
The generic current-scope download fix is now live in website `a3af4c49`,
after feature43547427334/main43547527468 guards and actual Pages43547527463.
Artifact14095221200 contains997,322,442 payload/999,915,520 tar bytes, both below
1e9; all31 served bodies match. All436 earlier download pins remain exact.
Every one of115 published asset bodies is hashed:35 native and80 linked
immutable/commit-pinned bodies; all113 original publication entries match the
frozen inputs. The local-versus-CI generated preview difference is separate
from those original scientific inputs.

Actual final desktop/mobile acceptance passes all51/306 reader frames per
width,220 county/mode selections,430 MO/WI/NE detail/link selections and every
count/registration/rate attribute on all2,177 NM shapes. Both real polygon
clicks select415/672 with the literal11/12/2026 11:07 AM MT clock. The current
full161,578,808-byte ZIP hashes correctly at both widths. All four county/
precinct package links are visible; historical scope clears the current link.
No source-data, DOM or style override is used, all browsers close, and actual
responsive images are reviewed. Maintained16 reader tests, Astro check/full
build, six independent site contracts and canonical11 regressions pass.
The older canonical renderer receives only its four-line legacy-link fix;
its unrelated code and all protected canonical HEADs/indexes remain intact.
No science refit, release replacement or second data activation was needed.
[Full observations](data/participation-access/20261114-native-regional-03/observations.json)
and [actual live acceptance](data/participation-access/20261114-native-regional-03/website-acceptance.json).

These are administrative observations, not identified switching, new voters
or staying-home counts. Texas's recorded+11.97610548 Democratic two-party-share
points equal+23.95221096 D-R margin points and remain unchanged; the33 qualified/
17 held behavioral comparisons remain separate. Older acceptance sections below
retain their original version-specific scope, superseded by this current entry.

## Additional declared source access outcomes: November 14

Two newly encountered native routes returned direct403. Neither response body
was read, so no successful body size/hash or numerical observation is claimed.
The serialized research-tool outcomes are retained; these exact routes stay
stopped without retries, alternate clients, caches, mirrors or guessed URLs.

| Exact declared route | Native outcome |
|---|---|
| `https://sos.iowa.gov/elections/pdf/2026/general/AbsenteeCounty2026.pdf` |403 Forbidden; completed2026-11-14T03:04:44.864Z; body not read |
| `https://elections.ny.gov/voters-registered-county-11012026` |403 Forbidden; completed2026-11-14T03:05:27.526Z; body not read |

A separate November14 `web.run` request to the supplied NORC download
declaration reported403 Forbidden. That attempted route is stopped; no alternate
client, cache, mirror or snippet recovery was attempted. This is explicitly a
web-tool result, **not an independently measured new native-origin denial**,
and does not erase the actual native200 receipts below. No new declaration
body, CSV or weights were acquired. The last verified November13 CSV remains
byte-identical to the supplied113,020-case original; reuse its qualified fits
without inventing a new weight version or a global dataset-absence claim.

The separately reachable Idaho May19 primary report is **not** November3
general-election participation. Its proposed89-row addition was rejected;
no primary counts, rate, county binding or model change is merged.
The cached Marion IA general-election header is a distinct, already-held
source under independent qualification, not an alternate route to either
denied product. No new Marion publication is claimed by this access receipt.

## 2026 South Carolina and Alabama native source counts

The supplied all-state directory was conditionally reviewed without retrying
stopped routes. Its complete51-jurisdiction dispositions remain in the
[complete numerical delivery](docs/DATA.md#current-south-carolina-and-alabama-native-counts).
New scientific sourceb837ce2 and reviewed selection correction0fd3fee are
published and canonically persistent. Immutable release444853341/-02 retains
all49 complete assets; the earlier444825497/-01 remains historical.

South Carolina directly reports **2,054,835 Total Voter Turnout**:
1,043,810 early +44,167 absentee +966,858 ElectionDay. These are native
reported-participation counts, not a candidate sum or independently deduplicated
people. Printed59.8% concerns active registrations, but its exact stock/cutoff
is absent. Neither November12 publication nor reported November11 certification
is a count-update clock. Printed mode percentages50.8/2.1/47.0 and their rounding
inconsistency remain unrepaired. This state-only observation supplies no local
county/precinct counts, demographic turnout or new behavioral identification.

Alabama's38 published BIFF county workbooks supply1,195 named statistical
columns and201,186 complete source-cell queries. County values are explicitly
derived complete source-column sums, not printed county parents or a new
common statewide total. The29 other county observations retain their older
sources. All67 county selections remain available; all1,195 source rows are
unmapped, with four actual zeros preserved and analytical rates/denominators/
count clocks withheld. Candidate/choice cells never replace native statistical
counts. Both decoding paths use xlrd and are not independent decoders; all38
native workbooks contain zero formula records.

Actual production QA caught an initial binding defect: the UF views selected
older duplicate county exports while available/official selected38 successors.
The reviewed generic correction pins whole equivalent old records and every
mode/partition occurrence, retains those aliases, and changes exactly76 UF
selection IDs plus the corrected package links. **Baldwin is86,472 in all four
modes**, not the stale86,040. No numerical source value was changed by this
binding correction, and ordinary refresh/publication baseline guards remain.

Counts917e37ec are live at catalogaf7a497e; nativeb2, model33, weights, House
endpoints,33/17 qualification and every other dataset entry are unchanged.
Both isolated97-test/57-output replays, three standalone SDKs, actual canonical
97-test/full-output replay and all31,835 client records/306 frames pass.
Real desktop/mobile checks verify all67 counties in all four modes, source
identities/clocks/stocks,1,195-row inventories, zeros and both full ZIP hashes.
Website4274's source-label deployment has an actual997,319,458-byte payload/
999,915,520-byte tar; the later correction is data-only. The approved independent
gallery withdrawal is preserved. See the [complete scientific record](data/participation-access/20261113-native-declarations-02/observations.json)
and [live acceptance](data/participation-access/20261113-native-declarations-02/website-acceptance.json).
This is not nationwide precinct completion; the regional integrations and final
audit/beautification remain separate work.

## Current House-model disclosures and variant sensitivity

The current interface shows each selected state/group point beside the range
across the **three existing model families and three association profiles**.
No fits, weights, source counts or comparison gates change: all50 state
decisions,33 qualified/17 held comparisons and1,600 group decisions remain,
including586 supported groups. A state's range is never substituted for a
withheld group. Contributions are to the statewide D-R margin, not the group's
own vote share. Democratic-share contributions are half the margin points;
retention keeps its own prior model-assigned D/R denominator.

The persistent badge prints the exact endpoint version separately from the
unknown native count-update clock and unqualified counting completion.
The conditioned total matches its endpoint **by construction**, not predictive
accuracy; preconditioning errors remain separate diagnostics. Modeled prior
D/R to no House choice and its reverse are not observed staying-home,
first-ever or returning people. Missing retention remains unavailable, not0%.
The independent critic gives a scoped semantics pass; its two static wording
caveats are resolved. This is not human certification or population validation.

The compact159,948-byte gzip is independently checksum-verified, decoded and
bound to the actual profile pins, endpoint and group. The default recorded
view does not request it or a full model. A failed optional fetch preserves
existing points and offers an exact-source retry. Nine-variant ranges are
model sensitivity, **not confidence intervals or all survey, transport,
accounting-frame or endpoint uncertainty**. Display bounds round outward;
net participation adds an explicit0.01pp display allowance for summing two
rounded entry/exit terms. Exact exported bounds and all earlier points remain
unchanged. All55,710 display checks pass.

Scientific sourceae9c997 and immutable444685503 provide all three already-public
aggregate profile bodies,7 Python tests, complete producer/packager code,
118,800 state/group/metric/variant witnesses and four exact outputs.
Two isolated network/DNS/child-process-blocked replays pass, as do14,850
actual client scope checks. This is complete **public fitted-aggregate
projection replay**, not private respondent-model fitting.

Websitef84b0f3 passes43 driver tests, Astro checks and the separate17
Which Candidate/caucus contracts. Actual feature/main guards43502379124/
43502827953 and Pages43502828046 succeed. Native artifact14075411840 contains
997,353,884 payload/999,956,480 tar bytes, both below1e9; all32 live bodies
equal the artifact. Every saved numeric cell and all prior driver payload
fields remain unchanged apart from the new sensitivity receipt;436 previous
download pins,113 archived models and independent Which Candidate/Interactive
Analysis HTML are retained. Live72 model/profile/group/unit cases at both
widths, full7,039,622-byte ZIP hashes, withheld selections, retention and
single-request caches pass. Two separately labeled503 fault tests preserve
points and retry successfully; no source/data/style overrides occur in the
normal live checks. Both production images are reviewed.

The entire live catalog047df0ce, counts01c3cd0a/nativeb2a69fc5, all native
observations and model33 remain byte-identical. Canonical source persistence
adds only the owned driver-test key to its intentionally older package
manifest, preserving unrelated scripts, old explorer and protected HEADs/
indexes. See [complete numerical downloads](docs/DATA.md#current-house-model-sensitivity-and-disclosure-replay)
and [acceptance](data/participation-access/20261113-house-model-disclosures-01/website-acceptance.json).

## 2026 Texas eight native county reconciliations

Eight county-published reconciliation forms add direct **total ballots counted**:
Liberty25,700, Hemphill1,262, Refugio2,448, Archer4,035, Cameron103,976,
Nolan3,781, Moore4,164 and Wise31,186. With the unchanged Harris1,392,280,
coverage is **9/254 counties**, with245 unknown, not zero. All254 earlier
mail and early-vote rows remain unchanged. No statewide total, registration
turnout rate, new precinct geography or individual histories are inferred.

Five new forms say Official Totals; Refugio, Moore and Wise remain preliminary/
unofficial. The eight attestation/posting dates are typed provenance, **not
count-update times**: count-as-of clocks and update labels remain null.
Hemphill's native difference3 versus computed0 and Moore's11 versus computed
minus11 are structured, unrepaired conflicts. Archer's blank difference stays
null. Refugio's voter-mode and counted-mode vectors differ despite the equal
2,448 parent; pending mail14 and estimated provisional1 are not added.
Cameron's native register103,976 equals counted ballots while its104,206 voters
exceed that stock by230. This is a confirmed native anomaly, not a duplicated
transcription or evidence of100% turnout; registration remains unqualified
context. Other pending/rejected measures also remain distinct.

The user-requested second agent compares all eight actual pinned originals
with selected facts and finds no blocking source/measure defect. This is not
independent human certification. The Cameron disclosure addition leaves the
reviewed native facts, visual transcriptions and175 native queries byte-identical.
Source7484828 is published and guardedly synced;56 focused tests pass.
Two83-test/90-output standard-library blocked replays, including actual
canonical code, and the22-member source SDK pass.

Immutable444663136 supplies20 fully authenticated/anonymous verified assets,
including the81,155,865-byte/210-member full analysis and7,916,024-byte source
SDK. They contain complete selected count/control facts, baselines, code and
queries, not every original form field or excluded publisher PDF templates.
Counts01c3cd0a/native bindingsb2a69fc5/catalog047df0ce are atomically live after
87 immutable-body checks, with zero activation requests/parses/compilations/
website builds. The836 Missouri/King contextual joins, other50 state shards,
statewide snapshot, model33, House endpoints and NORC weights remain unchanged.

Actual production passes1,088 selections across six modes and both widths,
all51 jurisdictions/306 reader frames, all254 county features with9 counts/
245 unknowns, and visible complete-source downloads with full ZIP hashes at
both widths. Website8264955 and all31 live HTML/script bodies are unchanged;
its previously verified immutable native artifact remains997,326,856 payload/
999,925,760 tar bytes, below1e9. Fort Bend, Nacogdoches, Panola, Travis and
Webb denied routes remain stopped. See [complete downloads](docs/DATA.md#current-texas-native-county-counts)
and [acceptance](data/participation-access/20261113-texas-county-reconciliations-01/website-acceptance.json).
Earlier campaign IDs below are retained historical receipts, not current pointers.

## 2026 Missouri Boone and Cole native statistics

Two independent county products add direct **Ballots Cast**, not candidate-vote
proxies: Boone67,527 and Cole29,108. The Missouri statewide declaration, separate
ENR application and Johnson County PDF returned native403 and remain stopped.
Neither denied product supplied originals or numerical values. No complete
new statewide House source or statewide participation estimate is inferred.

Boone's six-page report prints Final Official,130,157 Registered Voters and51.88%.
Its literal November9,2026,1:36PM clock has no supplied timezone.
Election Day46,516,Absentee16,488 and Central1/2/3/4 counts1,210/1,172/939/1,202
reconcile to67,527. Those native categories do not establish returned-mail stages.
Every factual page's numeric-token inventory matches an independent reader;
50 header,520 literal and eight typed statistical cells also agree.

Cole's physical page1 is a scanned complete30-row turnout table:28 locality
labels, ABSENTEE and native Total. Direct visual transcription retains every
label/count/register/percentage; there is no OCR or encoded-text extraction
claim. Locality ballots23,958 plus5,150 ABSENTEE reconcile to29,108.
Locality registers sum55,406; ABSENTEE repeats the same55,406 stock, so
110,812 is **not** a county electorate. Native Total52.54% and the distinct
November9,2026,10:05:40AM clock remain source context, timezone unknown.
The source filename says Unofficial while its page prints OFFICIAL RESULTS;
the literal printed status is retained, not independently certified.
All29 non-Total rows remain source reporting units, including ABSENTEE,
not29 matched precinct polygons. The remaining23 physical pages are contest
abstracts, outside the selected turnout-table extraction.

The shared routine adds31 separately pinned,558-fact-bound observations:
two county parents and29 reporting rows. Both analytical/view denominators and
rates remain null; native registration stocks and percentages remain inspectable.
Changed-count and changed-clock negative checks fail as intended.
Two82-test/57-output isolated full replays, actual canonical-code replay and
the31-query standalone SDK pass, with source-packet bytes identical.
All21 native assets in immutable444603376 are fully verified.

Counts55a8f41b activate at catalog46bd3ae3 after54 full-body checks, with zero
requests, parsing, compilation or website builds during cached activation.
Christian's prior observation, other50 jurisdiction shards, statewide snapshot,
native3bcc, model33, House endpoints and NORC weights remain unchanged.
Missouri now has **three source county observations out of115**, plus29
table-only reporting rows; the other112 counties are unknown, not zero.

The separately reviewed8a1da7f contextual successor adds only Boone/Cole to the
previous King review: all834 prior joins,1,329 prior selected records, exclusions,
source selections and20 geometry collections remain exact. The complete review
has836 joins/1,331 records. Its full25,589,619-byte/39-member package in
immutable444601898 includes the new native analysis and prior King analysis;
both blocked complete-member replays pass. These are unchanged2024 Census
county contextual shapes, not certified2026 election or precinct boundaries.

Website8264955 pins the review and retains earlier complete links. Seventeen
frontend tests pass in maintained and canonical trees. The actual production
browser passes86 cases,58 reporting-row selections,115 reference features,
three source counts/112 unknown counties, all51 jurisdictions/306 reader frames,
and both complete archive hashes at both widths. Pages43486985052 and main
guard43486984973 succeed; actual native artifact14069140286 has997,326,856
payload bytes and999,925,760 tar bytes, both below1e9. All31 live HTML/script
bodies equal the artifact; independent Which Candidate/Interactive Analysis
HTML,436 prior complete-download pins,113 archived models and prior numerical
drivers remain unchanged. Both final responsive production images are reviewed.
A second critic-agent visual transcription finds zero differences in120 CSV
and120 factual-JSON comparisons; it is not blinded human certification or
statistically independent evidence.

See [complete downloads](docs/DATA.md#current-missouri-native-county-counts),
[observations](data/participation-access/20261113-missouri-native-counts-01/observations.json)
and [acceptance](data/participation-access/20261113-missouri-native-counts-01/website-acceptance.json).
The independent critique also identifies nonblocking current-model disclosure
improvements; these are tracked separately, without removing provisional
conditional estimates or confusing the archived entropy model with the
current learned House models.

## 2026 King County native Ballots Cast successor

The separately declared current PDF prints **935,956 Total Ballots Cast**,
**1,460,414 Registered Voters** and **64.09%** identically on all17 pages.
The county observation replaces601,199; the334,757 increase is a change between
dated administrative snapshots, not new voters, switching or observed staying
home. The native PDF clock is **November12,2026,15:10:05**, timezone unspecified.
The separate complete CSV supplies no native clock; the PDF clock is not copied.

All115 contests,286 choice rows and1,430 CSV count cells are retained, together
with914 complete PDF factual-measure queries. Independent PDF verification
checks238 header,1,760 literal and34 typed-count cells, and all17 page numeric
token inventories. Candidate/contest votes are not summed into participation.
Legislative District32's State Senator accounting control is short by1, and
one CSV per-choice overvote counter is186 versus the PDF's185 total-overvoted
ballots. Neither is repaired or treated as an interchangeable measure.
The printed64.09% remains inspectable, but the analytical fraction and
registration-denominator qualification are withheld.

The native index and separately declared mid-election CSV returned403 and remain
stopped. The distinct current CSV/PDF wrapper roots returned200 and supplied
literal meta-refresh targets; only those targets were followed. No precinct
original, precinct geometry or final/certified result status is inferred.
The complete permitted factual inputs, native CSV, all numerical queries,
code/tests and source-disposition records are available in the
[27-asset immutable release](https://github.com/hanshanley/margin_of_error/releases/tag/participation-king-native-count-refresh-20261113-01).
The original PDF template is retained for review, not claimed as a public
archive member or re-extracted by the public replay.

Shared scientific source e69a266 and its four owned canonical files pass85
affected tests. Both complete82-test/57-output isolated replays, actual canonical
replay, isolated39-query SDK and standalone source-concordance replay pass.
Catalog0c6c232 activates counts06711a2f after54 immutable-body checks, without
source requests, re-parses or activation builds. Other117 Washington records,
other50 jurisdiction shards, early/mail frames, native3bcc bindings, statewide
snapshot, model33, House endpoints and NORC weights are unchanged by this task.
The independent automated9bf56a2 snapshot publication is preserved separately.

A production check found the old contextual join correctly rejected King's
changed full-record checksum, leaving the new sidebar count off the polygon.
The separately reviewed b1f5149 successor changes only King, retaining all833
other joins,1,328 other full source records, exclusions, source selections and
all20 geometry collections. It retains the strict full-record/geometry checks.
All834 numerical joins and1,329 full selected records, original identity inputs,
geometry, complete King analysis and reproduction tools are in the
[complete contextual successor](https://github.com/hanshanley/margin_of_error/releases/download/participation-king-context-successor-20261113-01/complete-context-successor.zip).
Both network/DNS/subprocess-blocked36-member replays pass. Website67455da pins
that immutable-source review without changing the county-boundary vintage,
adding precincts or promoting a rate. Its17 affected tests and Astro checks
pass in both maintained and canonical trees. Actual production desktop/phone
browsers verify312 map values across four full-election modes, King polygon
selection and the full contextual-download hash at both widths. King stays
gray because its rate is withheld, not because its count is missing.
Pages43479566667/main guard43479566728 succeed. Native artifact14065126605
has997,324,587 payload bytes and999,925,760 tar bytes, both below1e9.
All31 actual HTML/script bodies equal the native artifact; the independent
Which Candidate and Interactive Analysis pages remain byte-identical.
All436 earlier download pins,113 archived models and prior numerical drivers
remain. The original392 count-selection checks and all51/306 reader-frame
checks remain applicable to unchanged count data and reader code.

This closes no nationwide gap or behavioral-model prerequisite by itself.
See [complete downloads](docs/DATA.md#current-king-county-native-ballots-cast)
and the final [observations](data/participation-access/20261113-king-native-count-refresh-01/observations.json)
and [website acceptance](data/participation-access/20261113-king-native-count-refresh-01/website-acceptance.json).

## 2026 Wayne County native statistical counts

The official Michigan county source supplies **770 native reporting units**:
758 in the main report (724,872 Voters Cast), and 12 in the separately declared
Belleville/Sumpter/Van Buren supplement (22,132). The main report explicitly
excludes those three localities. Their **747,004 derived administrative
composite is not a separately printed county parent or a qualified count of
unique people**. Agreeing duplicate parent labels are checked, not added.

All 217 factual worksheets and their complete statistical queries are retained.
The three real zeros and 61 labels without a literal Precinct designation remain
selectable. Registrations and printed fractions remain context only: the main
workbook's 1,435,257 registrations differ from the older PDF's 1,474,536; the
supplement's zero/N/A is not an eligible-zero denominator. All analysis rates
stay withheld.

The main and supplemental Excel H1 caches decode to November 6, 2026,
08:32:47.569 and 11:57:18.452 respectively, with unknown timezones. Original
cache lexemes, number formats and date systems remain in the full queries.
These are not copied PDF clocks or a fabricated common snapshot.

Shared source2324a9e adds an explicitly reviewed append-only count operation
and a separately pinned contextual-binding addition. Counts e4bd2004 and native
bindings3bcc590d are activated together by catalog783199c, after all87 immutable
runtime bodies were anonymously verified. Michigan now has three selected
county observations across the existing83-feature Census reference, and833
reporting rows including the unchanged63 earlier rows. Only four county-mode
bindings are appended. Every old binding, geometry body,232 old Michigan
observations, other50 jurisdiction shards, statewide snapshot and provider
frame remain unchanged. No new precinct geometry is qualified.

Website ecd2f02 replaces the hard-coded two-county missingness message with the
actual loaded inventory. Its native Pages43454665378 artifact has997,287,791
payload bytes and999,884,800 tar bytes, both below one billion. Existing
House endpoints, model33, NORC fits/weights,113 archived models and436 complete
download pins remain exact. These partial county statistics do not justify a
new statewide Michigan turnout or demographic switching/staying-home estimate.

The [complete downloads](docs/DATA.md#current-wayne-county-native-statistical-counts)
include the100,678,076-byte/211-member analysis and all771 selected canonical
queries. All20 assets in immutable release444407182 are full-body verified,
authenticated/draft then anonymously/public. Both independent80-test/90-output
offline replays, the actual canonical replay, isolated source SDK and83 affected
source tests pass. Public replay uses complete sufficient factual inputs; it
does not claim extraction of excluded publisher templates.

The [acceptance record](data/participation-access/20261113-wayne-statistical-counts-01/website-acceptance.json)
records actual desktop/phone navigation, count/reference checks and full
downloads. The protected older canonical explorer is deliberately preserved;
the published maintained website source is authoritative for the live viewer.
This completes the bounded Wayne integration, not the remaining all-state work
or the later full audit and beautification.

## Recorded House swings: default display correction

Website9c06c56a566c6dc95e3d5569fd8ae14e09a3fcd3 corrects the November13
screenshot's gray Texas: the prior initial map applied a like-for-like
candidate-coverage filter, although the recorded totals were present.
The default now displays all50 recorded House changes. Texas is
+11.97610547994342 Democratic two-party-share points, equivalently
+23.95221095988684 D-R margin points. These are unchanged held source counts,
not new returns, measured switching or population turnout.

Seventeen changed-competition/election-scope comparisons are hatched, not
silently treated as comparable preference shifts. The33 conditional/17 held
behavioral policy, all model families/profiles, priors and weights remain
unchanged. A small source-count projection renders without downloading fitted
models; missing model data cannot hide known recorded swings.

Actual Pages43438470967 and both exact-source guards succeeded. Native
artifact14044617025 contains997,264,628 payload bytes and999,854,080 tar bytes,
both strictly below1billion. All prior driver payloads,113 archived models
and436 complete-download pins remain exact. Actual unqueried production HTML
and26 script bodies match the artifact. Desktop/phone checks pass306 recorded
map values,100 state selections,204 preserved comparable/switching values,
the17 hatch qualifications, model-failure isolation/recovery and50 no-JS rows.
Both responsive production images were reviewed; no valid-data/style overrides
were used. All9 source bodies are anonymously byte-verified and guardedly
persistent;39 affected canonical tests and Astro0errors/0warnings pass.

The complete scientific CSV/JSON/ZIP downloads are retained unchanged, not
replaced by these acceptance records. This display correction adds no county
counts, precinct boundaries, refits or new behavioral qualification.

## 2026 New Jersey administrative subtotal successors

The complete accepted21-county/32-context native compilation supplies15
genuinely changed county observations. Selection uses literal native table
clocks and the exact accepted parent labels, not filenames, page order or
municipal sums. The measure remains **Early Voting Votes Cast + Election Day
Votes Cast + Vote-by-Mail Ballots Tallied**, excluding provisionals. Issued,
received, pending and provisional counts remain separate native queries.
It is not a native all-mode ballot total, unique-voter count or measured
nonparticipation.

Atlantic94,256 retains its decrease36; Morris199,582 increases442.
Union's congressional total179,217 retains its overseas-inclusive scope,
while the municipal total178,802 and415 mail difference remain separate.
The12,574 change across15 observations is not promoted to a statewide total.
Salem's three latest same-clock reports conflict and remain held; its older
dated record is not silently relabelled. Cape May's42,442 native summary and
the other five unchanged county observations remain exact.

Source046897e extends the existing shared factual binder with an explicit
component-sum operation, not a new county importer. It checks exactly one
parent, distinct native columns and physical headers, or the pinned explicitly
reviewed image transcription for Sussex. Unchanged measure semantics, count
mirrors and literal source clocks are required. The18-row replacement family
excludes Cape May's already-distinct native source. Other92 NJ records,
50 other jurisdiction shards, current statewide snapshot, provider frames,
geometry/rate holds, native991, model33, study weights and House outputs remain.

All75 affected maintained/canonical tests,673 independent source/preservation
comparisons, two fresh69test/57output replays, the actual canonical replay and
isolated1,961,659-byte/23-member source SDK pass. The complete15,239,791-byte/
141-member analysis has SHA256
`f470eeb3229d1779e519147ceaeb0911c7d2df86f3c0261b71cc41ae71be335c`.
Its full native predecessor, all15,766 factual cells/controls,32 contexts,
21 county decisions, sufficient inputs, code/tests and complete outputs remain
downloadable. Excluded publisher templates/images are not falsely claimed as
part of public extraction replay.

Immutable release444238558/tag`participation-nj-derived-county-refresh-20261113-01`
has all16 full assets authenticated/draft then anonymous/public byte-verified.
The common cached publisher activates counts64e9f92 at catalog25abfa3 after54
immutable body checks, without requests, re-parsing or a website build.
Actual production verifies306 bindings/51 selectors/14 state-reference cases,
NC100/WY432 selections at both widths, NJ252 county selections and120 changed
source/clock/null-rate cases, both complete ZIP hashes and21 public contextual
bindings. Both images reviewed. All23 unqueried HTML/script bodies equal the
accepted5168917 application; its existing native artifact/caps remain unchanged.
See [full downloads](docs/DATA.md#current-new-jersey-administrative-subtotal-refresh)
and [acceptance](data/participation-access/20261113-nj-derived-successors-01/website-acceptance.json).
Broader source/model/geographic/historical work and the later audit/beautification
remain open; no nationwide completion or fresh NORC fit is claimed.

## 2026 Oregon state reference and registered-source revision 33

The held official Oregon general-election page reports **2,019,444 Ballots
Counted**, **3,109,145 Active Registered Voters** and two agreeing **64.95%**
displays. The native result clock is **11/13/2026 | 1:45 AM PT**; retrieval
is separate and no canonical timezone conversion is invented. Its complete
36,835-byte original has SHA256
`c3051595596d2796e2634d92b4f8ab537b4f89a8b1e5c5ff50422f0129738d68`.
The maintained HTMLParser extraction and independent lxml/libxml2 DOM agree
on all14 selected literal/value/assertion/context checks. Backend
`hidVoterTotal=1089701`, reported0 and not-reported1318 remain opaque,
not the active register or evidence of complete counting.

Three previous observations must not be conflated. The latest raw crawl
changes7,894 counted ballots and no registrations. The actual accepted runtime
reference was1,551,077/R3,109,089 (increase468,367/+56); model32's separately
dated selected reference was1,891,605/R3,109,084 (increase127,839/+61).
These counting/reference revisions are not observed new voters or switching.

Shared source29f7362 adds a distinct reviewed `state_reporting` operation and
registered-source successor. It does not weaken existing coherent-county or
fixed-registration guards. Only the current snapshot/index change; all51
jurisdiction shards remain exact, including the dated, unselected old Oregon
state record. Other current reporting, provider early/mail/demographic
observations and native991c5863 remain exact. County returned-envelope
observations are not replaced with the state counted-ballot statistic.
Counts76878ba is active through atomic catalog1f4e6b1 after54 full immutable
body checks, without a build, source request or reparse.

Model33 recomputes only the existing Oregon primary source-unit partition,
using the same1,655-case Civic weights/probability: conditional participant
units **2,083,361.267128987123...** and complementary units
**1,025,783.732871012876...**. The other50state/51control/33scenario rows,
all17 earlier complete numerical outputs and nine House family/profile
outputs remain exact. The separate Oregon monthly-registration scenario
(R3,112,307) and formal-analysis-warning envelope context stay separate.
No native outcome is fitted; these units are not measured staying home,
certified population counts, or independently validated model errors.

Both complete releases are public and immutable:444190384 (14data assets)
and444188768 (31model assets), every full body verified authenticated/draft
then anonymously/public. Both fresh data replays pass63tests/all57outputs;
both model replays pass5tests/all48outputs and whole-ZIP exact reproduction.
Actual canonical replays pass, as do80 affected source tests in both trees.
The source SDK separately replays21members in an isolated standard-library
process. Public replay includes all selected factual inputs/recipes/queries,
not re-extraction of the excluded publisher HTML/application. The original
remains private; no new source acquisition or respondent refit is involved.
See [complete downloads](docs/DATA.md#current-oregon-state-reference-and-model-revision-33).

Website5168917 is verified live and canonically persistent. All70 required
website tests/Astro pass; the actual canonical four projection tests,
full-release regeneration and Astro also pass without changing independent
package scripts or the older explorer. Native Pages43425281622 and both
source guards43425281512/43425281631 succeed. Actual artifact14037436051
contains997,241,489payload/999,833,600tar bytes, both below1e9, with436old
download pins,113archived models and every unrounded33display value exact.
Unqueried production HTML and all22served scripts match the native artifact.
Production passes306bindings/51selectors/14state-reference cases, all100NC
county/432WYunit selections at both widths, and four-mode79Civic/112flow/
2margin/34scenario/51decision checks plus full CSV/group-query hashes.
Four actual production images reviewed. The focused Oregon screenshot
selector uses an explicit scenario ID because Oregon has two legitimate
frames; both still receive complete numerical checks.
See the [acceptance record](data/participation-access/20261113-or-state-reference-01/website-acceptance.json).

## 2026 coherent North Carolina counts and native-source revision 32

Preserved accepted predecessor; revision33 above advances Oregon only.
North Carolina's counts and complete group/source queries remain unchanged.

The already-preserved official NCSBE originals contain genuinely newer numerical
data, not just refreshed retrieval metadata. Shared processing58ed929 uses
strict native JSON records and actual CSV headers, retains literal scalar types,
zeros and record indices, and reproduces all full original-source queries.
Independent verification covers 101 API records/1,212 scalar fields and every
header/value in the 3,240 state and 324,000 county aggregate rows.
All county joint cells match their state counterparts, including zero cells.
No new acquisition, formula execution, missing-as-zero repair or inferred
precinct geography is involved.

The official all-mode counter is **4,243,180**, with **7,885,046 registrations**
and 2,626/2,626 reporting units unchanged. All 100 source county IDs/literal names
match the accepted frame. Its actual runtime baseline was 4,223,102
(increase20,078); the separately dated selected model reference was4,223,355
(increase19,825). The latest two raw crawls differ by58, not the accepted-to-new
change. The state label is November12,2026,6:33p.m., timezone not supplied;
each county keeps its own `imp` value. Retrieval/HTTP timestamps are separate.

The preserved official catalog distinguishes **Absentee Counts** from
**Absentee Request Demographic Stats**. The selected CSVs are public aggregate
cast-count cells, including early-voting modes, not individual voter records.
Their actual headers, native request-type/mode labels, registration-party,
gender, race, ethnicity and count fields are retained. The older2020 tab-layout
description is not substituted for the actual current CSV schema.
Revision32 exports all7,575 native source-mode group projections and the entire
327,240-cell underlying query set. No matched group-registration denominator,
all-mode demographic turnout or source/survey gender equivalence is inferred.
Mode totals can overlap or have different cutoffs; do not sum feeds or use them
as evidence that particular previous voters stayed home.

The generic count routine coherently replaces the existing NC state reference
and100county observations together, preserving the old base snapshot's provenance.
Only `states/NC.json.gz`, `current.json.gz` and `index.json` change.
All50other jurisdiction shards,403other NC observations,six other reporting rows,
6,450early-activity/135provider demographic rows and existing native991c5863
remain byte-identical. All registration/geography/rate holds remain.
Counts967054a is active at catalog60bf14d after54full immutable body checks;
all other catalog entries are preserved, with no build or source reparse.

The separate registered-reference operation changes one existing NC state/control
reference, one scenario's bookkeeping and the old November6 snapshot's historical
disposition, not any fitted probability. All34scenario means/Rframes/weights/
qualification flags, other50state/50control/33scenario rows and12earlier numerical
outputs remain exact. The3,895-case NC Civic prior and all nine House outputs
are unchanged. Conditional units4,427,914.405402/3,457,131.594598 and the nominal
native-minus-model comparison are not observed voters/nonvoters or validated error.

Complete immutable datarelease444146422 has19,604,553bytes/141members/20assets;
model32release444146420 has270,632,645bytes/42members/24assets.
Every authenticated-draft and anonymous-public asset is full-body verified.
Both fresh data replays pass48tests/all57outputs; both model replays pass6tests/
all22outputs and whole-ZIP exact reproduction, with network/DNS/children blocked
and probed. Actual canonical114affected tests and full data/model replays pass.
The complete source SDK independently replays all originals/queries under
isolated `-I -S` execution, using only extracted dependencies.
[Full numerical downloads](docs/DATA.md#current-coherent-north-carolina-counts-and-native-source-revision-32).

Website3cfd938 contains the small verified model32 display projection and both
complete group/query download links, not large static copies or a new model mode.
All70affected website tests/Astro and canonical four-test/full-release projection
regeneration/Astro pass. Six owned files are guardedly persisted without moving
canonical HEADs/indexes or replacing independent package/older explorer changes.
Native Pages43417847986/guard43417847633 pass for3cfd938. Actual artifact14033436506
contains997,241,488payload/999,833,600tar bytes, both below1e9;22unchanged public
JS bodies,436old full-download pins and113archived models remain.
Actual unqueried production HTML equals the native artifact; all22served
scripts equal source. Production passes306bindings/51selectors and100NCcounty/
432WYunit selections at both widths, plus four-mode79Civic/112flow/2margin/
34scenario/51decision and full numerical CSV/group-query hashes.
Desktop/mobile screenshots reviewed. QA-onlya2fb768 corrects one checker
anchor-label assumption, not application/data bytes; no extra build.
The [acceptance record](data/participation-access/20261113-nc-native-successor-01/website-acceptance.json)
retains actual native/live/canonical proofs. Broader nationwide work and final
audit/beautification remain open.

## 2026 coherent native county and reporting refresh: revision 31

Preserved predecessor; the current NC/count/model successor is revision32 above.

Shared processing9c787a5 binds complete accepted native factual grids to
reviewed source/year/state, guarded Total Ballots Cast columns and exact
23county/432reporting-unit identities. Independent state/county/unit controls
agree at191,713, replacing191,688: six county and20unit numerical changes
sum+25. Provenance updates cover455records. Candidate choices are separate
accounting, never the source of the ballot measure. Native result clock and
timezone remain unknown; official workbook naming is not final certification.

The existing common CLI compiled both countscddb52cc and native991c5863,
then activated them atomically at cataloge7413a1 after87immutable files were
anonymously verified. Other51count files/29native files, all51jurisdiction
dispositions, provider early/mail frames, identities, registration fields,
rate/geography holds and other catalog entries are preserved. A full new
source-reporting export is included; no unsupported geographic overlay is added.

Ballot-only model31 updates one WY reference, not a registered scenario.
Its separate valid-choice context184,254 includes1,031source-unassigned
write-ins and excludes1,231overvotes/6,228undervotes. The older183,200 context
had a different scope; its difference is not participation or switching.
All34scenario CSV bytes, other50state/51control rows,781-case WY Civic prior,
fits/weights/qualifications and existing House outputs remain unchanged.

Complete immutable releases444062632(data:73,306,625bytes/207members/17assets)
and444062631(model31:251,010,401bytes/32members/19assets) have every authenticated
draft and anonymous public asset verified in full. Two fresh data extractions
each pass33tests/all90runtime-query outputs; two model extractions pass7tests/
all17outputs and whole-ZIP exact replay. Actual canonical89affected tests and
both full replays pass with network/DNS/children blocked/probed.
[Complete downloads](docs/DATA.md#current-coherent-native-counts-and-ballot-control-revision-31).
Website30371c8 advances the small display projection, preserves all34scenarios,
and fixes unknown source-clock rendering without manufacturing a clock.
Native Pages43405520853/guard43405520921 pass. Actual artifact14026913742 has
997,240,701payload/999,833,600tar bytes, both below1e9; all22JSfiles match
published source (21unchanged, one reviewed clock-label patch),436older
download pins and113archived models remain. Actual production verifies all306
state/mode bindings,51selectors and432WYunit selections at both widths,
all79Civic/112flow/2margin/34scenario/51decision rows in four browser modes,
full numerical CSV hashes and current ZIP links. Four new screenshots reviewed.
Owned canonical code/display, full replays, regeneration and Astro pass;
independent package, protected HEAD/indexes/unrelated files and older local
explorer remain intact. Its tiny published reader patch is separately retained
in the [acceptance record](data/participation-access/20261113-wy-native-successor-01/website-reader-change.patch),
not applied over unrelated local changes. Broader implementation, full audit
and beautification remain pending.

## 2026 complete native source context: revision 30

Generic processing7963b13 updates the obsolete non-selected Minnesota native
context in the complete current model ledger. Old2,490/4,105 reporting units/
1,224,405 counts become all4,105 reported rows/87 counties/2,852,618 Total Number
Voted from the already-accepted November10 source. The raw12-column file is
headerless: its column schema is explicitly reviewed, not a printed native
header. Every original literal and all unit/parent component/count queries
agree with the accepted complete source packet. Metadata cannot provide
replacement counts. Native clock11/10/26 8:08AM; timezone unknown.

Exactly one non-selected source context changes. All51state and34scenario CSV
bytes, selected November2 Registered-only3,927,036, all source means/priors/
weights, other51controls and full older Maryland/VT queries remain unchanged.
Native7AM3,927,697 and Election Day147,357 are separate source fields, not that
dated registration stock, a population or turnout denominator. All60component
conflicts,six electorate excesses,32zeros and null precinct rates are retained.
The stable legacy context ID is provenance, not a partial current scope label.
Its explicit measure now rejects generic physical-ballot/unique-person meaning.
No independently printed state count, new scenario, fit, outcome calibration,
source-count repair, local survey allocation or geographic work is invented.

The full179,023,914-byte/29-member ZIP SHA256
`535bc55c943e677a6ab1361b63dd1bbb9bd2872325ebb0405e902d560cbb5ccd`
contains both entire107,093,238-byte prior29 and71,548,414-byte native source
packets, code/tests, full14outputs and exact offline reproduction.
All16release443999393/tag`participation-state-controls-20261113-30` assets
are verified authenticated/draft then anonymously/public, full bodies.
Independent checks cover all4,105 original records/87 parent totals.
R/canonical34affected tests pass; both fresh extractions pass7tests and
reproduce the whole ZIP byte-identically offline under blocked/probed
network/DNS/children. All14numerical outputs additionally match individually
in both extracted replays. Actual canonical7test/14output/wholeZIP replay passes.
[Complete downloads](docs/DATA.md#current-native-source-context-revision-30).

Website539cc68 advances only current complete-download bindings; all previous
state/scenario display values are exact. Required69tests/Astro and guarded
canonical3path/display projection/3tests/Astro pass. Native43395764741/
sourceguard43395764723 pass for539cc68. Actual artifact14023137622 has
997,240,655 payload/999,833,600 tar bytes, both strictly below1e9;22frozen public
JS bodies,436old download pins and113archived models survive. Every unrounded
scenario value and current complete ZIP link match the actual artifact.
Production desktop/mobile/no-JavaScript/blocked-JSON checks pass all old
Civic/new current-version rows and full CSV hashes; screenshots reviewed.
Release443999393 is public and immutable. The
[scientific record](data/participation-access/20261113-native-context-successor-01/observations.json)
and [website acceptance](data/participation-access/20261113-native-context-successor-01/website-acceptance.json)
retain the evidence. This does not complete nationwide native rollout or the
broader implementation prerequisites for full audit and beautification.

## 2026 existing registered-frame model: native control revision 29

The complete current native-control28 baseline still used VT's November4
municipal totals506,512 registrations/311,009 native Votes Cast. The accepted
November9 full turnout report supplies506,830/311,510. The same247 town
identities and all283 reporting parts/14county controls/printed state control
are already qualified for native registration-frame reading, not population
harmonization. All90 count comparisons and624 printed percentages replay.

Generic processing sourcef6abaa4 binds replacement counts only to reviewed
native factual count columns, never metadata or percentages. It replaces the
existing `vt-2026-held-municipal-registration` control/scenario, not a new
model variant. Native active/inactive status, cutoff and study-frame
exchangeability remain unqualified. The source-weighted754-case Civic parent
has weight250.2665563419, modeled voter161.7026706267/nonvoter88.5638857152;
the64.612177108391...% propensity and all fitted priors/weights are unchanged.

Conditional native registered-frame voter/nonvoter units are now
327,473.897238458963.../179,356.102761541036..., versus earlier
327,268.430515254279.../179,243.569484745720.... The increases205.466723204683.../
112.533276795316... partition the318-unit registration change. No outcome
calibration to311,510, physical-ballot/unique-person promotion, local/group
allocation, confidence interval or observed staying-home claim follows.
The nominal native-count/model difference is explicitly not validated error.

All51state/DC rows,52native controls and34existing conditional cases remain;
exactly one row in each changes. The other50/51/33 rows and the complete Maryland
stock/card/accounting outputs are unchanged. The full107,093,238-byte/25-member
ZIP has SHA256`2692c9c978638b5fec0f15a4c7fd7d3b163cae9e3e3eb5b4a3df3be3eecd7492`.
It contains the complete106,571,158-byte native28 baseline, full370,732-byte
accepted native source packet, code/tests, full queries, exclusions and replay.
The fully pinned legacy source note outside its internal numerical manifest
is explicitly allowed; no extra unreviewed data or code members are accepted.

All37 targeted tests pass. Independent Fraction checks verify unchanged
probabilities and full unrelated-row preservation. Both fresh complete
extractions pass6 packaged tests and reproduce all11 numerical outputs and
the whole ZIP byte-for-byte with network/DNS/children blocked/probed, zero
attempts. Release443966016/tag`participation-state-controls-20261113-29`:
all13 assets full-byte verified authenticated/draft then anonymously/public.
[Complete downloads](docs/DATA.md#current-registered-source-frame-model-revision-29)
and [acceptance record](data/participation-access/20261113-registered-control-successor-01/observations.json).

Website54ce62c is verified live through Pages43392149287/sourceguard43392149124.
Its actual native artifact14022130292 has997,240,655 payload/999,833,600 tar
bytes, both strictly below1e9. All22 frozen public JS bodies,436 old download
pins and113 archived model records survive. All34 existing scenarios in31
jurisdictions and all51 frame decisions render inside the existing Civic research
details, with every unrounded model value checked in the actual artifact.
Production desktop/mobile/no-JavaScript/blocked-JSON checks pass all new rows
and every original Civic table; full CSV download hashes match and desktop/
mobile screenshots were reviewed. Required69 website tests and Astro pass.
Actual canonical science passes37 tests/full11-output/whole-ZIP reproduction;
five guarded website files, three new display tests, exact full-release
projection and Astro pass while preserving the independent package, HEADs,
indexes and unrelated files. The [website acceptance](data/participation-access/20261113-registered-control-successor-01/website-acceptance.json)
retains the deployment, artifact and browser proof.
All existing House family/profile endpoints,
33conditional/17held masks, count/catalog/native-binding versions and source
fits/weights remain unchanged. No new source original or respondent acquisition
was required. Full audit and beautification remain pending.

## 2026 county primary originals and native viewer resolution

The newer county comparisons prompted checks of independently administered
county originals, not mirrors of denied state/Civic routes. Full ledger/code/
record and stop-store checks found no prior acquisition for these county hosts.
Washington TN's actual `https://www.wcecoffice.com/` returned403; stopped without
following search-cached PDFs from that denied site. The three numerical
exceptions remain unresolved, not corrected by a demanded swing sign.

Howard IA's actual `https://howardcounty.iowa.gov/` returned200,143,589bytes,
SHA256`12f66656c340f3b975bead019141e2d65f3684b2e1a84cb055c0df2c03fa5694`.
Its literal "Howard County, Iowa Results" link declares the vendor object
`https://cap.gmdsolutions.com/viewfile.aspx?id=A187354CD62547FA9C4C51B383A1ACA0&dir=Objects`.
That exact request returned200,25,533bytes,
SHA256`44873a0e93302461164436ee9d8255a26e209dd675173afe1ec73a52e4dfee79`,
but the body is the generic PDF.js viewer template. Its hidden password-dialog
markup is not evidence that the actual document is password-protected, and the
viewer is not numerical election data.

An optional private trace in the shared collector resolves the actual redirect
to `/lib/pdf.js/web/viewer.html?file=...`, rather than guessing file paths.
The explicitly declared child document at the vendor's `/api/files/` endpoint
returned actual403 and is stopped. No PDF bytes, election identity or candidate/
turnout counts were verified. No browser, referer/cookie, alternative-client or
search-snippet replacement was attempted. Stable safe URLs/outcomes are in
[the access record](data/participation-access/20261113-county-primary-access-01/observations.json);
full private redirect URLs, publisher template code, headers and contact data
are not exported.

The private trace supports200 and304, including Python3.9's HTTPError filename,
while leaving public receipts, cache schema and host restrictions unchanged.
Stopped/challenge attempts clear traces. All39 affected tests pass. No numerical
endpoint, fit, weight, mask, catalog or map changes follow from these access
results. The complete24-member numerical release443915242 is retained unchanged,
not replaced with an access-only download. Genuine source/model work and the
final audit/beautification remain open.

## 2026 newer county House source concordance

The acquired immutable combined county snapshot
`26eb70ea95056fcb4af64146ae63eb82b71e3beb` is6,331,085bytes, SHA256
`3665656ea459c44dd4b25e168232ccb7a4b26978ba4f03552cd2957b5ad89ef5`,
Gitblob`fb0fe1b30f0b01b83c06bc28b5b8e30af7335882`.
Its commit time is November13,2026 04:16:06UTC; acquisition is06:39:54.318249UTC.
This is the newest acquired snapshot, not an assertion that the publisher
cannot subsequently revise it. The complete source receipt is retained.

The same-commit builder was inspected for source semantics: county current
D/R/I shares are rounded to two decimals,2024 shares to one; some2024 shares
first pass through two-decimal rounding. The reviewed historical recipe
therefore conservatively includes both rounding stages for mixed source origins,
not just the last displayed decimal. The emitted margin
is derived from rounded shares. `sp24` compares the2026 office margin with the
2024 presidential margin, not the2024 House result. D/R/I need not sum to100;
I is not assumed to be all Other. Expected/remaining/reporting fields are not
population denominators or nonvoter counts. No exact party counts are recovered
from percentages, even when an integer happens to fit a rounding interval.

The shared reviewed comparator retains every3,143 factual source unit for both
snapshots, all3,127 older exact reference counties, all12,405 native county
candidate rows,435district controls/audits, source receipts and precision recipe.
There are3,155 union queries across all50 states plusD.C., including28 source-
only and12 reference-only units. Sourceh24/h26 presence is3,086/3,112 with3,084
pairs; h24 fields do not change between the two recent source snapshots.
All3,127 exact reference party vectors match their full native candidate rows.
Reference county coverage remains49 states; Maine's16 counties are missing
because of its existing ME-02 candidate/unlocated-vector hold, not zero votes.

Compared with8049f27,187h26 records change:175contest totals across20 states
and12reporting-field-only changes. Compared with the older exact reference:
1,904 arithmetic-compatible rows,1,180 contest-total differences,48 AK/CT
geographic holds,16 missing reference units,one explicit reference zero,two
same-total rounded-share disagreements andfour missing secondary results.
Closed precision intervals are conservative arithmetic diagnostics, not
independent source validation, candidate/round matching or behavioral eligibility.

The important exceptions remain numerical queries, not automatic corrections:
Alexander IL1,601 versus old exact0; Howard IA equal3,702 but differing party
shares; Washington TN equal40,682 but opposite D-R margin signs. The TN export
copies literal native candidates and verifies their vectors, rather than
assigning votes by position. Its older D23,535/R16,010/O1,137 is not silently
swapped using the secondary rounded D39.35/R57.85. Declared original IL-12
`https://civicapi.org/api/v2/race/87123` returned actual403 through the shared
stop-aware store; stopped with no alternate route. AK/CT geography and ME-02
holds remain. Prior qualified official HI/WY endpoints retain precedence.

Processing source03fb69f passes26 focused tests. Both fresh archive extractions
pass16 packaged tests and reproduce all six full numerical outputs offline
with network/DNS/children blocked/probed, zero attempts. Independent decimal
checks agree for all6,172 current-share comparisons and all2,777 historical
margin intervals. Immutable release443915242/tag
`participation-county-return-concordance-20261113-02`: all nine assets full-byte
verified authenticated/draft then anonymously/public. Complete ZIP2,066,895bytes/
24members, SHA256
`e4e9014cd2abf7f948e54bebbe296b20af998f792e32ffdb35bc6db2c7163c3b`.
The original publisher prose/application code is excluded; all sufficient
selected factual inputs, native values, queries, code and tests are included.
Earlier release443910979 is explicitly superseded because its historical
intervals omitted upstream rounding; all its assets are preserved, not replaced.
Current count/share classifications and model endpoints are unchanged by this fix.

[Complete downloads](docs/DATA.md#newer-county-house-source-complete-reconciliation-downloads)
and [acceptance record](data/participation-access/20261113-county-concordance-02/observations.json).
No new exact endpoint, ballot/participation observation, model variant, fitted
NORC revision or study weight is claimed. Nine existing family/profile outputs,
33conditional/17held masks and count/native/website versions are unchanged.
Native conflict resolution, broader implementation and final audit/beautification
remain open.

## 2026 Vermont native turnout report and municipal refresh

The permitted VT results index explicitly declares the
[2026 general-election turnout report](https://outside.vermont.gov/dept/sos/Elections_Division/election_info_resources/elections_results_data/2026_general_election_voter_turnout.pdf).
The acquired434,143-byte PDF has SHA256
`1a8826e99f2c263ed13940b4136c63f80af0e0dbe0c88502cd7d6bfcd8af4b5c`.
Its13 pages/14 grids identify the November3 election and November9 report
date, but do not supply a time, timezone or certification status.

All283 town/legislative reporting parts, 14 printed county controls and the
county/state summary are compiled. All247 existing town names match using
whitespace-only reading normalization. Distinct Rep/Senate reporting-part
identities and all90 cross-level count comparisons agree;624 printed
percentages agree at their displayed precision. The independent reader compares
978 count positions, including42 native blanks, plus138 headers/1,600 literals.
Blank county headings are not zero observations; controls are not added twice.
The full2,252-cell JSON/CSV queries retain native values, statuses, literal
labels, source rectangles, percentages and their separate denominators.

The native state controls are311,510 Total Votes Cast (Includes Absentee),
506,830 Registered Voters and193,189 Absentee Votes Cast. The absentee count is
an included component, not an additional participation total or a returned-mail
measure. Native turnout61.46% uses registration; native absentee share62.02%
uses votes cast. Neither is an eligible-population or individual behavioral rate.

The common routine replaces the complete247-town source scope. Ten counts and
40 registration stocks differ from the older snapshot. Six previous
contest/scope registration-rate holds are explicitly reviewed against the new
same-report numerator/denominator frame, supporting247 native registered-voter
fractions. Prior observations/holds and the new review remain in the full
packet. This does not qualify unique people, physical ballots, precinct
boundaries, demographic allocation or staying-home/switching histories.
Other50 whole-state shards, both VT provider early/mail frames and all
existing municipal binding qualifiers remain unchanged.

Processing source25f7c37:37 tests pass. Both fresh archive extractions reproduce
all57 complete batch outputs and three full source numerical outputs with
network/DNS/child gates blocked/probed and zero attempts. A genuine cached no-op
preserves bytes/mtimes. All11 release443852099 assets/tag
`participation-vt-native-turnout-refresh-20261113-01` are verified in full while
authenticated/draft and anonymously/public. The complete12,541,210-byte ZIP
has SHA256
`da8b158b0b6c8d3245d21f74fb5a23536e11a6db5173f7042b699a71c52b51fc`.
It includes the complete370,732-byte native-source packet, all51 sufficient
baseline/runtime files, full queries, code/tests and replay inputs. Original PDF
templates/private glyph facts are not redistributed; replay starts from complete
permitted factual grids.

Data catalog9ba97246 activates counts784e30c6 from staged1c7a033c after all54
immutable files are anonymously verified. All306 production bindings and51
selectors pass. Coupled website082575f fixes stale hard-coded rate summaries
and the native PDF source-link label;124 targeted tests, Astro check and
desktop/phone checks pass. Native Pages43373889995/source guard43373890018
succeed; actual artifact14013818063 has997,195,451 payload/999,792,640 tar
bytes, both below1e9, preserving22 source scripts,436 old download pins and
113 archived models. Actual production verifies all247 mapped values/fractions
on desktop/phone plus all six modes and11 changed/prior-held town details,
with no valid-data overrides.

Canonical shared code passes37 tests and reproduces all57 batch files/three
full native outputs offline. Only the coupled disclosure/link changes are
surgically merged into the differing canonical frontend; its unrelated local
loader and geometry gates are preserved, not wholesale replaced. Canonical
HEADs/indexes and protected user files remain unchanged. Public acceptance:
`data/participation-access/20261113-vt-native-turnout-01/`.
Survey fits/weights, House endpoints and behavioral masks are unchanged.
Broader all-state source/model work and the requested final audit/beautification
remain open.

## 2026 native Cape May count refresh

The full native NJcompilation below now supplies one actual same-measure
count successor through the shared routine. Cape May's older41,278native
`Ballots Cast - Total` snapshot becomes42,442; the same76,899registered-voter
denominator and approved county identity are preserved. The exact reported-
registration fraction is55.191875056892805%, native printed55.19%. Native
clock is `Election Summary - 11/12/2026 03:34PM`, timezone undeclared.
ED127of128/complete0of128 remains incomplete/unofficial, not certified turnout,
eligible-population participation, unique people or observed staying-home.

Source899505c adds eleven cross-input factual assertions for the reviewed
successor and forwards the unchanged approved21county reference. Candidate
choices cannot authorize participation counts; missing facts cannot become
zeroes; clocks/URLs/source hashes must agree with the full factual input.
The complete19-row accepted source scope is retained, changing only one
observation. All50otherwhole-state shards, everyotherNJrecord/providerframe
and all126nativecounty-context qualifiers remain unchanged.

Immutable release443823002/tag `participation-nj-native-count-refresh-20261113-01`:
all eight assets authenticated/draft and anonymous/public full-byte verified.
Complete12,344,673-byte packet SHA256
`db36b93326ffa0e1af86bb09e088f728b8378d486ae2dd5b766b03bebb70998e`;
128members include the full sufficient all51baseline, full candidate runtime,
source originals/factual grids/reference, code/tests and complete queries.
Both fresh extractions pass17tests and reproduce all57full outputfiles with
network/DNS/child commands blocked/probed. Actual canonical17tests/replay
likewise pass. A real no-op preserves every runtime file byte and mtime.

Atomic data catalogfb3af059 activates counts64c872ab from staged0ba592b4;
all54immutable files anonymously verified before catalog activation. Other
catalog entries/nativebindingsb82a5795/website73d15a1 are unchanged, with zero
websitebuilds/static payload growth. Actual production verifies all306
state/mode bindings/all51selectors plus all six Cape May modes on desktop/
phone, true native printed fractions, current complete links, unchanged
provider early/mail frames and public county-context bindings; no valid-data
overrides. This does not claim a new county/precinct geometry or SVG overlay.
House models and survey fits/weights are unchanged. Broader all-state
administrative/model integration and final audit/beautification remain open.

## 2026 New Jersey complete native PDF measures

All21latest county files declared by the official periodic-report directory
were acquired through the shared stop-aware client and pinned individually.
Their58pages contain86reviewed numerical grids,1,472source records and
15,766measure cells. Preserve source/retrieval/filename clocks separately:
several Nov12filenames contain earlier printed clocks; Morris also includes
older administrative schemas. Cape May's ten-page appendix is an actual
contest/statistics summary, not an administrative time series.

Shared processing source3901e61 preserves original/reading coordinates,
nonzero origins/crops/rotations, explicit blanks/zeros, absent columns,
native negative entries and literal geographic labels. Independent
pdfminer/pdfplumber decoding agrees on15,410encoded numerical cells.
Sussex's348image cells are separately visually reviewed transcription;
239on-device OCR numeric tokens agree and municipal controls match.
No encoded text or zero values are invented for the scanned original.

All1,428within-report checks remain downloadable, including19cross-level
control differences;140additional missing/unqualified comparisons are
excluded, not interpreted as zero. Bergen's repeated county control was
equality-checked. Keep Salem's same-clock content conflicts and Morris's
issued-versus-eligible provisional definitions and overlapping units.
SVRS receipts, issued/tallied/pending mail, eligible provisional ballots and
machine counts do not share an interchangeable voter/population frame.

Cape May's native statistics report42,442ballots and76,899registered voters,
with55.19%printed registration-frame participation. Its House choices total
41,957and68overvotes+417undervotes reconcile to42,442. Reporting remains
incomplete/unofficial; no eligible-population, unique-voter, certification,
individual stay-home, precinct geometry or statewide aggregate is inferred.

Immutable release443806852/tag `participation-nj-native-measures-20261113-01`:
all eight assets verified in full while authenticated/draft and anonymously
after publication. Complete1,268,193-byte packet SHA256
`ac8bfa0fad2b8ddf32091e2b6d795b71664f46b087c0bb5b1740f198c3d2e1b1`;
two fresh extractions each pass23tests and reproduce all three full numerical
outputs with network/DNS/child commands blocked and probed. Public replay
starts from complete permitted factual grids, not original-template
re-extraction; unnecessary staff contacts/templates are not redistributed.
[Full numerical downloads](docs/DATA.md#new-jersey-complete-native-tables-integration-pending).
The source-compilation release itself changes no website/model data or study
weights; the separate Cape May count successor is described above. Further
binding and combined-source estimation remain required. The declared OKportal's
actual403remains a persistent STOP, not a reason to try another client.

## Recorded House counts versus behavioral eligibility

Website source `0a164b6b4f184aba0e5783d44c6cd0264234864f` separates the
unadjusted recorded-count view from the existing comparable/model view, exposes
held-state raw counts in state details and a complete50state table, and defaults
to Democratic two-party-share change units. The original33conditional/17held
behavioral decisions, source fits, weights and all nine profile/family numerical
querysets are unchanged.

Texas's held2024D/R4,310,913/6,234,918 versus2026D/R5,147,146/4,591,278
implies+11.97610548 Democratic-share points, or+23.95221096 D-minus-R margin
points. Its behavioral hold no longer erases those recorded numbers.
Raw candidate totals are explicitly unadjusted: negative Alaska/Massachusetts
changes from coalition labels/changed competition are not Republican preference
swings or eligible behavioral targets. No signs or source counts are repaired.

All37focused tests pass in two fresh offline extractions, which reproduce both
completeJSON/CSV numerical outputs byte-for-byte with network/DNS/children
blocked and probed.550independent count/share/eligibility checks pass.
Actual local desktop/phone browsers verify25,398exactmapvalues,100state
selections, Texas's+11.98 value, model holds, pointer/keyboard selection,
source/scale fault recovery, cache, complete links and no horizontal overflow.
Actual production desktop/phone passes the same25,398mapvalues/100state
selections, Texas benchmark, model holds, pointer/keyboard, source/scale faults,
cache/download and no-overflow checks without valid-data overrides.
NativePages43336523492/sourceguard43336523474/artifact13998151323 is
downloaded and verified: actual997,189,386payload/999,782,400tar bytes, both
strictly below1e9;436old download pins/113original models preserved and the
actual compiled renderer checked. These are native artifact/production proofs,
not local size projections. Records:
`data/participation-access/20261113-house-recorded-counts-01/`.

Immutable science443665464/tag `participation-house-recorded-counts-20261113-01`:
complete53,684,336-byte packet/SHA256
`f5ce94c8b7f03329f0b5974467e9913ec1f6437f33b151602086f71bfef4321e`.
All seven full assets verified authenticated while draft and anonymously after
publication. Every selected recorded query, exact processing/interface code,
37tests and sufficient fixtures plus the ENTIRE50,449,445-byte predecessor are
included. No wholesale predecessor resimulation claimed. This uses the held
November7snapshot, not newly acquired HI/WY counts or a NORC weight revision.
See [usage and interpretation](docs/HOUSE_RECORDED_COUNTS.md).

## 2026 combined-source refresh and model reconciliation

The user's current instruction is to use official2026 returns, weighted NORC,
exit/current-voter polling over time, Census/ACS local context, registration/
history and mail/absentee/early-ballot measures together to update the estimates,
not merely list their availability. Current task details are in
[REMAINING.md](REMAINING.md). The single45-minute continuation is124.

| Newly checked declaration | Native outcome, November12 at23:16UTC |
|---|---|
| [NORC project](https://www.norc.org/services-solutions/civic-health-elections-project.html) | HTTP200;181,832bytes; SHA256 `6bf924a71e60f6d2d393ca526bafa6a9acd9abf336e22c3759b1df6ae3ca223a` |
| [NORC download declaration](https://civichealth.norc.org/download-data.html) | HTTP200;2,962bytes; SHA256 `505d5e7d5992251639f669fd589e48a86176733473414c4174793101deddd2f1`; declares public-use ZIP/CSV and codebook |
| [SSRS supplied methods link](https://ssrs.com/news/what-you-need-to-know-about-the-election-day-voter-poll/) | Native307; no successful original claimed and not falsely labeled403 |

NORC's native declaration explicitly says the data will change as weights
are adjusted to final vote counts. The supplied
[CSV](https://civichealth.norc.org/downloads/civichealth_datafile.csv),
[codebook](https://civichealth.norc.org/downloads/civichealth_codebook.zip) and
[crosstabs](https://civichealth.norc.org/crosstabs.html) are the supplied version-
check leads. Subsequent ordinary native requests on November13 at00:28-00:30UTC
returned200 for the codebook ZIP241,714bytes/SHA256
`5c0e522820d36562d2610ea514ae693079f871b3352584ee070b628b02ac59c8`
and CSV88,182,202bytes/SHA256
`496a5b57fbc435210bdf78e2c1c3717879c0689c74081bee830d121b548c792f`.
Both are **byte-identical to the supplied originals**. No respondent reduction,
weight change or source refit is warranted merely by reacquiring these files.
The publisher's older application-code comment saying its codebook is unavailable
does not override the actual200/validZIP; no global absence claim is made.
Original respondents and publisher application code remain outside public Git/
downloads; no copied browser API credentials were acquired or used.
The actual weight-target/calibration qualification is unchanged, not resolved
by matching bytes. A source weight calibrated to current results is not independent
validation of those same results. Empty web-renderer output is not a native
access denial; the two NORC pages above were reachable in those native
November12 requests. The separately recorded November14 web-tool403 is
not substituted for that earlier native evidence.

The actual all51jurisdiction directory refresh retains every disposition:
48declared results-index URLs,24requests,18acquired indexes and30access holds,
including persisted stops. Fresh declared official HI summary/precinct TSVs
and WY candidate/ballot PDFs plus its complete three-workbook precinct archive
are held. WY native House99,906Gray/61,689Kinney differs slightly from the old
provider99,891/61,684; separate native ballots191,713 across23counties.
The complete native products are now compiled and the qualified changed
endpoints reconditioned in research source
`25dcb6be51253a8a3140b55cf222627b03fee2d7`. The bounded update is now
verified live in website73d15a1; see [remaining work](REMAINING.md) for the
broader all-state, source/model and geographic tasks, which remain open.

Every202HI summary/25,766precinct record and every declared WY cell across
52sheets/33,534rows/539,246cells is retained and independently checked.
All192printed WY House/ballot controls agree; all432native precinct reporting
units reconcile through23counties to the state. Thirty-five date-stored native
precinct labels are decoded only using their literal reviewed display formats
and independently checked, not matched by row order or guessed geographic alias.
No formulas are executed, native counts repaired or boundaries qualified.

HI native HouseD256,268/R105,749/O9,359 matches the full precinct/mode
candidate sums. Its249reporting/247nonreporting split records include positive
VSC votes underReporting0; that flag never erases votes. Deduplicated native
ballots392,435 exceed Housecandidate+blank+over/invalid392,428 by7; the signed
gap remains unresolved. Native registration853,399 is not allocated again
from the repeated whole-state contest stock or used as local voter eligibility.

WY native HouseD61,689/R99,906/O22,659 includes1,031explicitly unassigned
write-ins in the outside-known-D/R category. Their affiliation remains blank,
not inferred as D/R or Nonpartisan. Its1,231overvotes/6,228undervotes remain
separate; candidate-choice counts plus these equal191,713ballots.
This explicitly extends the earlier named-only current scope; source59d359c
and the first private packet are predecessors, not final accepted scope.
Current full candidate inventory is1,401, with all435districts/50states retained.

All nine updated profile/family cases preserve the earlier learned priors,
weights, source-validation scores,33conditional/17held masks and every other
48whole-state/assumption/seed query.37Python tests and465,552independent
checks pass; two final fresh offline extractions reproduce all82full outputs
and both50state recorded-count exports with37Python/18client tests each and
2,200independent exported-value checks. Complete packet82,439,184bytes/SHA256
`1dfd78d5bb83477a603c6e97e1b21a23437e7bc732d70e304538baac520b801b`.
Whole workbook templates remain separately held; public reproduction uses
complete factual grids. No new raw respondents, source refits, weights,
individual histories, geographic joins or population validation are claimed.

Immutable release443764898/tag
`participation-house-official-refresh-20261113-01` now publishes the complete
packet, full native factual grids/queries, both recorded-count formats, all450
state/profile/family comparisons and complete verification/reproduction proofs.
All11full assets are verified authenticated while draft and anonymously after
publication. The current website source73d15a1 passes38affected tests and actual
local and actual production desktop/phone25398mapvalues/100state selections
without valid-data overrides. NativePages43356596811/sourceguard43356596795
and downloaded artifact14007030928 verify997,194,869payload/999,792,640tar
bytes, both below1e9, all436old download pins/113archived models and the actual
new compiled renderer/current source receipts. Guarded canonical source sync,
37backend/38frontend tests, all82canonical offline output matches and both
complete canonical JSON/CSV matches pass; protected HEAD/index/unrelated files
are unchanged. Earlier missing-test/selector checks are unaccepted predecessors,
not unresolved final errors. This is not full all-state native coverage,
individual-history identification, a NORC weight revision or a new precinct map.

The native civicAPI refreshes for race87495 and87098 returned403 and are stopped;
the declared AlaskaNovember11combined report returned405. No other client,
cache, mirror or search-snippet numbers replace those failed originals.
Independently declared official products remain separate sources, not mirrors.

Texas's existing raw counts imply+11.97610548 Democratic two-party-share points,
or+23.95221096 D-minus-R margin points. Its model-comparison hold is not a
Republican result. Keep descriptive reported totals, units, candidate-coverage
qualification and behavioral attribution distinct. Current-voter polls do not
identify missing prior voters, Census residents do not become observed voters,
and registration/returned/accepted/tabulated measures must not be interchanged.
The schedule change is operational policy, not new scientific results.

## Reviewed routine participation batch

Source `2082405294cccfeec3bb5325973afd33b70fbbc7` adds the maintained
`scripts.participation_batch` command and [usage guide](docs/PARTICIPATION_BATCH.md),
extends the shared adapter rather than calling state-specific importers, and
freezes three previously reviewed public canonical reporting snapshots.
These are accepted derived source observations, not fresh native extraction.
The registry preserves their original provenance and exact replacement scopes.
All 51 baseline jurisdictions remain, including 48 with no newly registered
source in this demonstration.

Actual proof: 4,963 unchanged rows across AR/AZ/WY, 113 county parents,
83 unknowns, 22 observed zeros; all native fields, display bindings and
54 compressed/runtime descriptor files preserved. Actual publisher returns
unchanged at351130a. The second actual CLI invocation performs zero requests,
parses, compilations or publication attempts and leaves the entire cache's
bytes and mtimes unchanged with networking, DNS and child commands blocked
and probed. All60 affected tests pass. Two fresh archived-code extractions
each pass14 workflow tests and reproduce all56 runtime/full-query outputs
byte-for-byte, also checking full source-row equality.

The shared workflow enforces access stops, personal-record rejection, approved
declaration-link discovery and retained discovery originals, exact inventory,
full election/geography/measure semantics and reviewed display identities.
Conditional HTTP validators survive unchanged input registration. Changed-data
publication uses separate staging and a complete-download byte/hash binding;
interruption/concurrent-catalog/corrupt-cache failures are tested.
Direct native-adapter/discovery changes are fixture-tested, not a claim of
new nationwide native products. Newly compiled native-binding products,
broader completeness and new measurement/geographic qualification remain open.

Immutable science release443580352, tag `participation-routine-batch-20261112-01`:
complete15,280,995-byte packet, full selected observations, complete 51-jurisdiction
and source queries, exact processing code and14 workflow tests. All six assets
verified full-byte authenticated before publication and anonymously afterward.
The existing website3cee/catalog351130a remain unchanged; no new rate, polygon,
model, build or data activation. Full records:
`data/participation-access/20261112-routine-batch-01/`.

## Historical precinct bulk collection: 2016 through 2024

See the [maintained usage guide](docs/HISTORICAL_PRECINCTS.md) and complete
[255 state/year decisions](data/historical-precinct-coverage/20261112-03/queries/all-255-state-year-decisions.csv).
All 51 jurisdictions including DC have selected sources and compiled queries
in each of 2016/2018/2020/2022/2024. This is not a count of fully covered states.

MEDSL2016 commit `5965d5e572dfb9affaf8b295e6ddee94773a6cf8`: all five office
partitions/22 originals, MIT notice retained, complete 4,060,918-row federal query.
All37 native fields independently compared. OpenElections: 85 statewide-named
CSVs plus414 supplemental county/ward/town/unsuffixed-general CSVs, all pinned
Git blobs verified, 13,003,540 rows. All native cells/modes and canonical fields
checked independently; alternative files never summed. Four repository MIT
notices retained, not extended to every source. Official AL/KS/PA2018/2020:
23 originals/1,161,107cells-or-rows and15 full Kansas grids; complete source
packet reproduces all19 outputs offline. NC2018 separately declared official
ZIP supplies183,723rows; all16 native columns and canonical fields checked.

The shared access-ledger parser incorrectly treated an entire Markdown table
as blocked when one row reported403. Fixed row-level interpretation with a
regression; the historical NCSBE page had not been natively denied in that
attempt. Ordinary acquisition then returned200 for the historical index and
its declared2018 ZIP. The distinct `er.ncsbe.gov`403 stays stopped. Concurrent
identical cache objects now use atomic publication; original shared-module
import provenance is supplemented, not falsely described as wholly verbatim.

| Historical route | Actual outcome |
|---|---|
| `https://elections.maryland.gov/elections/archive/2018/election_data/index.html` | Native HTTP403; stopped, no alternate client/cache/mirror |
| `https://elections.maryland.gov/elections/archive/2018/index.html` | Native HTTP403; stopped, no alternate client/cache/mirror |
| `https://apps.elections.virginia.gov/SBE_CSV/ELECTIONS/ELECTIONRESULTS/` | Officially declared directory, native HTTP403; stopped |
| `https://www.ncsbe.gov/results-data/election-results/historical-election-results-data` | Native200/101,014bytes; declared historical archive acquired, not an ER denial bypass |
| `https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2018_11_06/results_pct_20181106.zip` | Native200/2,084,856bytes; ZIP CRC passed, full TSV retained |

Independent licensed MGGG products close the remaining source-presence gaps:
`mggg-states/MD-shapefiles` at `c040ffd20f2560f4edcfe9829720a01aa13eca7b`
and `mggg-states/VA-shapefiles` at `63dabd2a58a5ea41b94406235da8a6d1fc6fa1da`.
MD2018 has two DISTINCT 1,809-row tables: merged election-day-only, versus
publisher-allocated early/absentee/provisional plus election-day counts.
VA2018 has 2,439 publisher-compiled attributes; VA2020 has 152,025 native
candidate/reporting-unit rows, including central absentee/provisional units
and multi-seat races. All original cells and selected election fields were
independently checked; the DBF checker uses a different binary reader.
Databases use ODbL1.0, individual contents Database Contents License1.0.
Retain original notices and MGGG attribution; VA2018 was compiled by Princeton
Gerrymandering Project and edited by MGGG. These are independent compiled
products, not retries or mirrors of the stopped official routes.

Existing MEDSL2022/2024 national holdings and original NYT presidential layers
were reused, not recollected. ME towns/WI wards/partial NJ and
unmerged KS sheets remain explicit; candidate votes do not become ballots or
group turnout. No new geometry join, cross-year identity, rate or map activation.
Source `650151b54f51f089e2d253425cadf2d300783255` contains 28 owned source/test
files and 46 passing tests. The final 874,127,644-byte complete packet contains
all six complete component packets and every selected held2022/2024 numerical
query. Every member checksum and all six nested packets pass; a fresh archived
network/DNS/child-command-blocked run passes all46tests and reproduces every
coverage/NC2018/MD2018/VA2018/VA2020 output byte-for-byte. This is not a claim
of wholesale multiyear re-extraction. Native template rights/version holds
remain separate from the complete selected factual queries.
Immutable release **443532631**, tag
`participation-historical-precincts-20261112-01`, supplies the
[complete selected numerical delivery](https://github.com/hanshanley/margin_of_error/releases/download/participation-historical-precincts-20261112-01/complete-analysis.zip).
All eight full assets were verified authenticated before publication and
anonymously afterward. This is research-download delivery, not a website build;
records: `data/participation-access/20261112-historical-precincts-01/`.

<a id="house-result-comparability-audit-in-progress"></a>

## House-result comparability audit and correction

The displayed Massachusetts raw House-margin change is **-22.90507143 pp**:
2024 D 2,386,143 / R 304,460 versus held 2026 D 1,722,855 / R 507,904.
These raw totals are not equivalent to a statewide voter-preference swing.
The already-held House Clerk original, page 35, lists named Republican nominees
only in MA-08 and MA-09 in 2024. The held 2026 provider snapshot lists them
also in MA-03, MA-04 and MA-06. Major-party ballot coverage changes **2/9 to 5/9**.
Other/independent and unassigned write-in votes are not reassigned to Republicans.

Common D/R source district IDs MA-08/MA-09 have D/R totals 517,363 / 304,460
then 409,193 / 212,901: **+5.64724422 pp Democratic**. This is only a subtotal
diagnostic, not a statewide estimate or a certification of unchanged boundaries.
A generic **435-district / 50-state / 1,400-current-candidate-row** audit is now
integrated before return conditioning. Named parties are counted by candidacy,
not positive support; native missing counts and multiple same-party nominees
require explicit scope qualification. An all-candidate-zero guard prevents
empty contests passing merely because names match. FL-10's literal zeros are
preserved and already held, not promoted as zero voter support. No repeated
same-district candidate names across party rows were found.

Sixteen coverage/count/stage policy holds plus independent Maine ranked-choice
scope leave **33 conditional comparisons and 17 held states** in every
family/profile. All three original families and six existing association
stresses receive the same decisions. Source fits and counts are unchanged;
affected conditional scenarios alone are recomputed. Source-only held
scenarios are explicitly separate in downloads and unavailable as current
election explanations on every map/static table. A changed MAE population is
not improved source prediction or validation.

Maintained scientific source `cc50fc288739b1c8150a68ab1df07468b580eace`;
byte-identical immutable viewer dataset at `4891ee0678c0105d8b5a228e340b587e157fce7d`.
Science **443411454**, tag `participation-house-comparability-20261112-01`:
complete **50,449,445 bytes / 133 members**, SHA256
`684edab6893d42eda52225b37fc53a663570322c39541c5f173fe47f3359b7bd`.
All nineteen full assets verified anonymously. Every sufficient input,
district/candidate query, all nine full state/group/assumption/seed outputs
and code/tests are included, never metadata-only. 465,552 independent checks,
166,188 actual reader/scale checks, six source and 34 frontend tests pass.
Two full 79-output network-blocked standard-library replays are retained;
122 analytical code/input/result members remain byte-identical through the
final viewer-only changes, so no redundant resimulation was done. The final
archive itself was not rerun wholesale; final archived source tests and reader
checks were rerun, with the explicit delta proof preserved.

**Verified live:** website `3cee7a193cb57428887a172c00d355fb06351c10`,
native Pages `43290808730` / source guard `43290808766` / actual downloaded
artifact `13977511623`, payload **996,886,705** / tar **999,475,200**, both <1e9.
All 436 old download pins and 113 original model objects remain. Production
desktop/phone verifies 23,562 exact map values, 100 state selections, real
Massachusetts pointer/Enter/Space selection, all family/profile/unit controls,
current 450-row CSV, withheld cases, cache, source/scale failure recovery and
no horizontal overflow. Adjacent border strokes no longer steal fill clicks;
shared demographic bounds include reported totals from states whose selected
group is held. Four production images reviewed. Old targets remain archived,
clearly superseded. No native totals were changed to force a desired direction.
Full records: `data/participation-access/20261112-house-comparability-01/`.

## Held reporting rows connected to county navigation

The accepted native tables already contained AR **2,768**, AZ **1,763** and
WY **432** reporting rows, but canonical county frames omitted them and their
legacy parent/selector metadata did not match existing county controls.
The repair connects all **4,963 rows to 113 existing county parents** by unique
literal same-state labels. It preserves every source count/clock/status/denominator,
**83 unknowns**, **22 true zeros**, all old records, other 48 state shards,
early/mail frames, native tables, county bindings and geometry originals.
No new numerical observations, rates, physical precinct joins or state allocation.

Frozen adapter source `5d59f39a53a76aefdcd01eeae230e58a34a5e4a9`;
science **443300298**, tag `participation-held-reporting-navigation-20261112-01`.
Full ZIP **38,063,832 bytes / 160 members**, SHA256
`15948ef18f6bd772a17e1e50e71fc8fb00f3ec69fa698a9ed84b1d7a4b492726`.
Every sufficient accepted count/native input, complete 4,963-row match queries,
all 57 outputs and maintained code/tests/readers are included, not metadata-only.
All eleven full assets verified, 85,128 reader checks and two fresh guarded
offline reproductions pass. Both missing-selector and wrong unknown-count-scope
failures were reproduced before the fix; explicit local fixtures preceded release.

Actual production verifies desktop/phone 244 county / 276 unit selections,
24 contexts, six real map clicks, missing versus zero, full downloads and no
new rate/polygon. Website `109754a734f043fbbbe4d792138caea3cd9da5f0`,
native Pages `43271725430` / guard `43271725174` / artifact `13967849374`:
**996,866,407 actual payload / 999,454,720 actual tar bytes**, both below 1e9.
All 436 old download pins, five source scripts and 113 old model objects survive.
This is preservation, **not proof that the old House endpoints are comparable**.
Count-only staging `5fa34d67abe0b9f5ba4169b7733567c643dcb912`, catalog
`351130a058e7e64bd970e62dce6e4edb3874b373`; all 54 immutable files verified,
old catalog retained during staging, every other dataset entry unchanged.
Records: `data/participation-access/20261112-reporting-navigation-01/`.

The sole 45-minute continuation is now **121**, replacing stopped 120 at the
user's request. Its obsolete historical queue is removed; the immediate priority
is source-result correctness, then remaining integration and reusable batching.

## 2026 Harris Texas held counted-ballot integration

An already-held and previously verified official report was missing from the
county-map runtime. It is now connected, rather than acquired or OCR'd again:
`https://www.harrisvotes.com/Portals/harrisvotes/Documents/2026/Reports/1126%20Preliminary%20Election%20Reconciliation%20-%20Unofficial%20Totals.pdf?ver=UZziX2HoKRKkYolHPwg9EQ%3D%3D`.
Original 29,813 bytes, SHA256
`64d92c0f8787191e42d3889caf60ecc5e56a7f1e2a8fdfd406152afcdc60f7b3`.
Native report date **11/4/2026**, with no report time or timezone. The HTTP
Last-Modified value is not substituted for the source clock.

**I. Total ballots counted (G+H) = 1,392,280**, separately **C. Total Voters
(A+B) = 1,393,495** from rosters. All 13 native factual rows remain, including
**5,300 rejected/pending** and signed **C-F-I = -4,085**. Roster minus counted
alone is 1,215, not the native reconciliation field. No disagreement is repaired
or pending/possible additions counted prematurely. Preliminary/unofficial status
remains; no certified, final or unique-person claim follows.

Registered Voters **2,761,770** has undeclared status/cutoff scope: **no new rate**.
`48201` is contextual Census identity, not a FIPS field printed in the report.
The unchanged full 254-county 2026 reference supplies context, not precincts.
Texas full-election county observations are now **1/254** in these map views.
Best available prioritizes this native count; all **254 early + 254 mail** county
observations remain in their separate modes, not mixed with counted ballots.
All 1,018 old Texas records, other 50 state shards, Wisconsin's two counties/
32 ward rows and existing native geometries/tables are preserved exactly.

Scientific source `3bed691632efac95cb1b62c18fee79dc2331f06b`, immutable science
**443243371**, tag `participation-harris-county-counts-20261112-01`.
Complete ZIP **68,729,952 bytes / 192 members**, SHA256
`ce1daade50e084cfdba52daf7dc1cb31136ede87b9f633bd0f1b291b55c453e2`.
Includes all 13 factual rows, safe provenance, full sufficient baseline runtime
inputs, unchanged county reference, every new output and maintained code/tests.
No raw HTTP/session headers, private voters or respondents. Both fresh guarded
offline replays reproduce all **87 outputs**; **457 actual frontend checks**,
two focused tests plus two Wisconsin regressions pass. Explicit unpublished
desktop/phone renderer fixtures were checked before immutable publication.

All ten full release assets are anonymously verified. Catalog
`8808a7c0d80324f32a2c3f37afe05ed1e365798a` atomically activates both dependent
datasets after all **86 immutable files** are verified; intermediate catalog
remained unchanged. Actual production, without overrides, passes eight Harris
map clicks/four source contexts on desktop/phone, both 254-county early/mail
views, full source details/date/download, 253 unknown-not-zero counties, no rate,
Wisconsin zero/noncontiguous-ward regressions and all 113 original model objects.
Five actual source scripts and website `94db6c0` remain unchanged; zero builds.
Full records: `data/participation-access/20261112-harris-tx-01/`.

A distinct fresh Utah declared index (343,311 bytes, SHA256
`9cbb3cc2b90d72dda788abdd3fa505440bc0e39f86d57d77ca5a0ad4f349c688`,
captured November 12, 2026 at 16:38:21 UTC) yields no newly qualified missing
county report; regenerated blob UUIDs and backend zeros are not new observations.
Utah remains 23/29; denied Cache workbook routes stay stopped. Butler Ohio's
rendered 148,684 control has an underlying original HTTP403 and is **not**
promoted as a native county count or recovered through alternate clients.
The nationwide geographic task remains open, with the sole 45-minute continuation.

## 2026 Jefferson Wisconsin county and ward-group participation

Official source: `https://apps.jeffersoncountywi.gov/jc/election/results/11032026`.
The complete original was acquired once: 134,561 bytes, SHA256
`5446fcc254a6a280214022e247754aa59ab5123ca855a8aa8cf93f0085babfe7`.
All 32 literal Registered Voters / Ballots Cast rows reconcile to separately
printed county totals **52,428 / 38,414**. One native 0/0 row remains zero,
not a computed turnout rate. Combined/noncontiguous wards are not split.

Native clock **11-06-2026 01:13 pm**, no timezone. Preserve both Official Results
and unofficial-until-canvass wording, plus the warning that 100% can refer to
one machine. No certification, all-machine/all-mode completion, unique-person
or eligible-population claim follows. `55055` is a contextual Census identity,
not native FIPS. Unchanged full 72-county 2026 references support the county
display; no new precinct polygons are approved. Ward fractions stay withheld.

Corrected source `3f44d4364e223204fcfb83873656f598a058d82e`; immutable science
**443214044**, tag `participation-wisconsin-jefferson-counts-20261112-03`.
Complete ZIP **65,478,892 bytes / 196 members**, SHA256
`7274b1714763b8a7a13c11c8021b526e4bf120f97700cc4e8e200f5d74f1244f`.
Includes original Jefferson report, every native query, complete sufficient
accepted runtime inputs, both full new runtime datasets, code/tests and replay.
All ten full assets verified, 684 frontend checks, two focused tests and two
fresh 90-output guarded offline reproductions pass. No respondent data.
Earlier scientific/runtime versions remain immutable; selector compatibility
metadata was corrected after actual browser QA, without changing native counts.

Counts and native bindings switch atomically in catalog `2176b9a673526ddb78c4945324286cd0db8530a1`;
all 86 full files verified. Actual unchanged production `94db6c0` passes eight
county clicks and 128 ward selections on desktop/phone, missing/zero distinctions,
source clock, full downloads and old model preservation. No website build.
Wisconsin is **2/72**, not complete. Brown's separate official PDF and Milwaukee/
Dane results URLs returned 403; safe receipts retain exact routes/status/hashes,
with no retries through other clients, mirrors or caches and no cached counts.
Records: `data/participation-access/20261112-jefferson-wi-01/`.

## Four-axis administrative participation and House-choice dependence

New source implementation `a2b3f9e854de4c35fc42958861579d561820662c`
fits 30 conditional House-pair heads while reusing 60 accepted paired
administrative-9 / House-30 heads from the earlier paired-source experiment.
Joint probabilities are `p(A22,A24|X2020) * p(H22,H24|A22,A24,X2020)`.
Conditional training uses the administrative pair as a target factor; test
forecast features enumerate **all nine hypothetical pairs**, never the observed
future history. Positive KL projection optionally preserves both accepted
per-case pair margins, isolating cross-axis association. This is a regularized
factorization of the full 270-category joint, not an unrestricted saturated fit.
Same five prior-only folds, two predictor levels and three native frames.

Primary history-only projected full-joint log loss **2.371022 -> 2.280635**
and Brier **.676764 -> .666091** improve. Prior-nonvoter future-15 log loss
**1.551515 -> 1.483908** and known-future-P/N **.490998 -> .460688** improve,
but prior-major-voter known-history drop-off **.069624 -> .070773** worsens.
Its full-15 log loss worsens while Brier improves. No universal staying-home
improvement is claimed. In primary history log-loss fold stress, joint
advantage reverses in 0/126 compositions, prior-nonvoter future-15 in 9/126,
entry known-P/N in 21/126; drop-off known-P/N worsens in 120/126.
Overlapping training folds make these stresses, **not confidence intervals**.

Of 6,175 retained raw cases, primary positive-weight evaluations use 4,015
overall, 2,760 prior positive-history/major-House cases and 403 prior explicit
nonvoters. The latter's coarse reference has 230 positive / 128 nonvote /
45 unknown future histories; weighted shares 71.144209 / 16.370869 /
12.484922%. Projected history predicts 72.336692% positive versus baseline
70.843548%; aggregate calibration therefore worsens despite better proper
scores. The six-cell prior-major reference fails the frozen every-cell-30
rule and is held whole. Native finer/source-state cells remain private.

Immutable science **443141393**, tag `participation-house-four-axis-20261112-01`.
Full **63,962,523-byte / 29-member** ZIP SHA256
`38ec0cc2532385460fe8d1ff4eace310061dd84f79282e54070724de58a76527`.
Entire accepted 63,651,646-byte predecessor, all 540 score queries / 216 pooled
scores / 60 predictive queries / 54 estimates / 270 simulation rows / 18,144
fold-stress rows, code/tests and permitted sufficient inputs included. Nine
focused tests / 3,650 independent math.fsum, cached-head, target-isolation and
pair-margin/dual checks pass. Two fresh blocked-network/command standard-library
replays reproduce all nine outputs and 600,000 synthetic source-predictive
draws; extracted tests pass six and skip only three optional numerical cases.
All **21 full assets** anonymously verified.

Prior-year conditioning is a retrospective source diagnostic; pre-2024
availability of the later matched record is not established. Postwave weights,
retained-2020-adult selection, conditional shared-item House codes, missingness
and source conflicts remain. Future-known-P/N scores are outcome-selected
diagnostics, not forecasts of cohort membership. Administrative nonvote is
not the 2026 NORC likelihood class. No current model/default/map, population
benchmark, first-ever/eligibility/death/migration or state-to-local allocation
changes. No old fit, simulation, acquisition or website campaign repeated.
Full results: `data/house-four-axis/20261112-01/`.

## Fixed-marginal House calibration and current association stresses

The held CES 6,175-case panel now supplies a nested dependence test with every
case's original full 2022/2024 House marginal predictions fixed. The same
2020-only predictor levels, five outer folds, three native frames and ridge
settings remain. Sixty accepted outer heads are reused unchanged; 180 new
inner heads exclude the outer holdout from fitting and calibration. Nine
prespecified D-D/R-R kernel strengths are selected only by inner-OOF full-pair
log loss, with ties preferring independence. No other overlapping outer-OOF
predictions or 2026 returns enter selection. No administrative-N persistence
parameter is estimated.

Primary history-only House-pair log loss **1.313660 -> 1.263987**, Brier
**0.483039 -> 0.477228**. Demographic/geographic scores improve
1.348023 -> 1.300594 and 0.492568 -> 0.485929, without beating calibrated
history-only. Maximum per-case margin error is below 2e-12; dual certificates
and independent math.fsum scoring pass. History selections 8/4/8/8/8 satisfy
the frozen source gate. Matching selected-source D/R margins subsequently
gives 4.785352% history and 6.424792% demographic switching against the same
4.599023% conditional source reference; switching itself was not the criterion.

The gate permits two explicitly **unvalidated postaggregation 2026 stresses**
(sqrt(8), 8) on the three already fitted current-family priors, not a population
correction. State and group-year margins and partition-state coherence stay
fixed; source-only feasibility backoff precedes any current-return comparison.
All six simulations are complete. Neither profile improves current 48-state
before-conditioning MAE for any family; the original default stays. Unknowns,
disclosure masks, direct-2022 scenario, AK/ME holds and earlier downloads stay.
Reported/model nonvote is not verified staying home, and retained-2020-adult
recruitment, conditional shared-item House codes, predictor/election-direction
differences and omitted newly eligible entrants remain.

Scientific source **dd28869d0985080f6ec2b31f90d6682f47033e90**, data/viewer
pin **3c99ff2712e266f16860551ab65957c647956753**; immutable science
**443019940**, tag `participation-house-fixed-copula-20261112-01`.
Complete ZIP **63,651,646 bytes / 124 members**, SHA256
`08273545ef2886a3994ea2f4a7c7083f7a780e78c3335c88b1d3665cc6b0db72`.
Both full accepted predecessors, all 270 curves / 30 decisions / 60 outer
score rows, six complete simulation runs, 450 comparisons, code/tests and
permitted sufficient inputs are included. All 22 assets anonymously verified;
15 scientific tests / 4,797 independent nested checks / 462,020 current
accounting/margin checks pass. Two fresh standard-library, blocked-network/
command replays consume 12 independently certified projected inputs and
reproduce all 60 outputs without baseline resimulation or private refitting.
Recomputing the projections themselves requires NumPy; the failed initial
replay and dependency-only correction are preserved, not hidden.
No persons, per-case predictions, coefficients, fine cells, CIs or unsupported
local allocations are released.

Existing-map controls are **verified live**, website
`94db6c0c098842b01cf0a33a090bf62c30cf818c`, Pages **43233632514** /
artifact **13951483145**. Actual 996,851,521 payload / 999,444,480 tar
bytes pass both strict caps. All 69 exact unqueried assets and 436 old full
download pins match. Production checks verify 90,576 new profile values,
45,288 original family values, 3,060 baseline values, 50 state summaries,
102 actual pointer selections and all 48 responsive/tab cases, plus no-JS,
failure/checksum/retry/cache and late-profile/office isolation. Actual phone
and desktop views were inspected. Full numerical and operational records:
`data/house-fixed-copula/20261112-01/`.

## Held-out cross-election dependence and identical-margin flows

The already-held CES 6,175-case panel now supplies a new five-fold predictive
test, not just another source inventory. Only contemporaneous 2020 presidential
response, approximate 2020 calendar-age, native education code and survey-state
predictors are allowed. Later choices/histories, carried recall profiles, IDs
and 2026 returns are excluded. Five fixed structural hypotheses compare
pooled-history pairs and independent/paired ridge with/without demographic and
geographic features. Separate administrative 9-class and reported-House 30-class
pairs retain unknowns and contradictions; no full four-axis dependence is claimed.
The source's conditional House code transport and 2020-adult retention limits
remain. Earlier 2022 weights are sensitivity frames, not valid 2024 voter weights.

In the exact previously public both-positive-history/both-major-choice cohort,
identical-margin independent-demographic predicts **11.294996%** switching,
paired-demographic **4.620939%**, against **4.599023%** reported. Margin fitting
preserves forecast odds, not observed switching. Paired-history predicts
4.549400% and has better overall proper scores than paired-demographic:
House log loss **1.275865 versus 1.315931**. Adding demographics/geography
therefore did not improve this source's overall prediction. Closer aggregate
calibration alone does not select a model. These expanded-target scores are
not comparable to the accepted 2026 model's different five-class scores.

Source `a90a2c6fb881fe1123c5da4a7f232d0d4d33e02b`; immutable science
**442867090**, tag `participation-house-paired-oof-20261112-01`. The full
163,404-byte / 29-member ZIP retains the entire accepted predecessor, all
75 model/fold/frame sufficient rows, 100 scores, 40 synthetic cells / 10 stages,
15 decisions, 5,040 stress rows, exact source/tests and both design versions.
SHA256 `a48dcae4c99911cf8c3dc05ef39bde1617d4abb12589d99d47dec15649c97ed8`.
All 19 full assets verified; 13 tests, 27,479 independent native-row, cache,
math.fsum/IPF checks and two fresh seven-output standard-library replays pass.
Of 180 successful component fits, 72 survived a score-only reduction correction
unchanged and 108 remaining fits completed; none repeated. Both policies,
original source and AST-bound adoption proof remain. No private people,
features, predictions, coefficients or native fine cells are published.
Fold-composition stress is not a CI. No accepted model, current source marginal,
live map, deployment or old download changed, and no 2026 transport is validated.
See `data/house-paired-oof/20261112-01/` and the complete download catalog.

## Conditional same-office House source concordance

The already-held CES 2020/2022/2024 recontact panel (DOI `10.7910/DVN/CETPVT`,
version 2.0, 6,175 cases) supplies 2022 and 2024 post-election House response
items and separate administrative participation histories. Choice coding uses
an explicit **conditional shared-item code transport**, not panel-native numeric
labels. Literal candidate-slot party fields determine party; missing party,
including `__NA__`, remains unknown. Code 7 alone is explicit administrative
nonvote; positive House answers do not resolve missing histories. Contradictions
remain separate; 2024 codes 6..8/12 and `_nv` counterfactuals are not borrowed.

Among 2,368 positive-2024-postweight cases with both histories positive and
both House reports D/R, weighted switching is **4.599023%**. The D-to-R and
R-to-D cells have only 33 and 37 respondents. A separate AP2024 pooled poll-close
state-weight source query has 79,516 selected modeled-current-voter cases with
known actual recalled House22/current House24 source responses: **3.372462%**.
The **-1.226561 pp** AP-minus-CES difference is unmatched source concordance,
not identified recall bias, national population switching or 2026 model error.
Frames differ in recruitment/retention, weights, response timing, recall,
state composition and administrative selection. These conditional D/R-only
denominators omit other choices and nonparticipation; they do not validate exit
or entry. Current-record states are not election-day residence.

Source `b97cb7ff535d39b8853e84f98944e31e332328df`; immutable science
**442761753**, tag `participation-house-panel-validation-20261112-01`.
All 319 public query decisions / two available tables / 317 whole-table holds,
eight permitted coarse sufficient cells, five full outputs, code/tests and
exact coding records are included in the 35,562-byte / 19-member complete ZIP:
SHA256 `25d0dfe7a6b7332dd6f26620b36b96f277e57e8f319f38bc70b83757d9c3e2d3`.
Fourteen tests, 14,138 independent SQL/exact-fraction checks and two fresh
standard-library/network-command-blocked five-output reproductions pass.
All 15 full assets anonymously verified. Native respondents/identifiers/private
fine cells remain local; inherited native-release/population holds remain.
See `data/house-panel-validation/20261112-01/` and the complete download catalog.
No accepted model, simulation, source weight, live map or deployment changed.
This does not close the 49 missing independent state-population benchmarks.

## Three fixed NORC House model families

Scientific source `7b760e61d7d601476f124b8302038147115ec08a` adds genuine native
histogram boosting and extra-randomized-tree fits, not merely more Monte Carlo
seeds. Accepted ridge fits and eight outputs are reused unchanged. Same source
records, predictors, weights, holdout seeds, 48 endpoints, disclosure masks and
simulation inventories are retained. The source-only preregistered rule keeps
ridge; boosting improves current-response log loss slightly but worsens
historical transfer. Historical transfer is now selection validation, not an
independent post-selection test. Current-return errors never select a model.

All 150 state/family decisions, 300 dispersion rows and nine source validations
are public in `data/house-model-families/20261112-01/`. Margin MAEs are
6.12699827 / 5.74311543 / 6.06357405pp; Democratic two-party-share MAEs are
exactly half. Gross retained-voter percentages are not halved. Full science
tag `participation-house-model-families-20261112-01` includes the entire
accepted predecessor, all permitted inputs, every state/group/seed/assumption
query and exact fitting/replay code: 35,332,487 bytes/53 members, SHA256
`124c3702ea3d7218351f0105a571407804d48a2afa9c924b743fb5dc8dd214da`.
Two fresh blocked-network/command standard-library-only reproductions match
31 full outputs; eight focused tests, 52,258 checks per new family and 3,788
cross-family checks pass. Raw respondents, private fine cells, individual
predictions and estimators are not published. AK/ME holds and frozen counts
remain; exact return reconstruction is not identified behavior.
Website **c2d1c19** is verified live: Pages43184405254/artifact13927688816,
actual996829655payload/999424000tar bytes, both strictly below1billion.
All69 unqueried production assets and436 old download pins match. Actual
phone/desktop checks cover45,288 family/unit/group values,3,060 baseline
values,102 real pointer selections,all50 summaries,22 groups/six dimensions,
noJS/failure/checksum/retry/late-office isolation,1,020 preserved legacy values/
126 summaries and48 layouts. Four actual production captures were inspected.
Full scientific/website records are in the same versioned data directory.
Full methods: [NORC House transitions](docs/NORC_HOUSE_TRANSITIONS.md).

This is the canonical **source-family ledger** for the research project and its
[companion website](https://github.com/hanshanley/margin_of_error). It includes
primary data, official compilations, academic harmonizations, secondary feeds,
user-supplied studies, and methodological references. An entry does not imply
complete coverage, independent validation, or permission to redistribute originals.

The per-file URLs, native timestamps, retrieval receipts, and checksums remain in
the machine-readable inventories linked below. Those inventories, not a copied
list of thousands of county URLs, are the inputs for future automation.

## Alaska Senate: two native parents and accounting scopes

The already-held civicAPI race `86916` contains two different aggregates inside
one response. The top-level candidate parent totals **214,246 candidate
selections**; the nested `alaska` State region totals **213,733**. No count is
repaired, blended or selected by closeness to an external outcome.

All four top-parent candidates exactly equal the source's **30 Borough units
plus its explicit Federal Overseas Absentee unit**. The **40 House District
units plus that Overseas unit** instead match the nested State region. Boroughs
alone and districts alone are retained as components, not statewide totals.
These are native vendor reporting roles, not approved county geography,
matched boundaries or proof of nonoverlapping legal election units.

The normalized D-R margins are **-2.039983099** and **-2.003017137** percentage
points for the top and nested parents, respectively: approximately **0.036966
points** of source-scope sensitivity. All native Republican candidates remain
Republican; Nonpartisan stays separate. This is vote-count accounting, not
individual vote choice or an explanation of the much larger House shifts.
The source reports native round **1**, **73.9% reporting** and a global clock
of **2026-11-08T01:37:46.780Z**. Registered population is null. A common response
clock does not establish synchronized subunit counts or final-RCV compatibility.
No cast-ballot, turnout, eligibility, county allocation or final-result claim follows.

All **234** previous candidate-control rows and every original field survive.
The prior **229** accepted controls are unchanged; four AK controls gain only
a separate noncounty internal-accounting scope, giving **233 internally
reconciled controls**, not 233 county or independently validated controls.
All four nested-parent disagreements remain explicit. Maine's **882 statewide
write-ins versus zero supplied county write-ins** remains held; the held town
vectors also contain no write-in count to allocate. All **14,742** earlier
crosschecks, **215** differing counts, six completed reference-ID joins and the
one additional named-count difference remain intact.

Maintained source `45bef126d7fa53c9264ae745fa585bc4cd73eb77` provides all
**288** AK native rows, **24** candidate/scope checks, **six** exact-fraction
margin diagnostics and complete control decisions. Five focused tests,
**4,253 independent raw-JSON/SQLite checks** and two fresh warning-fatal
network/external-command-blocked reproductions match all seven output files.
The initial district-to-top-parent hypothesis was rejected, not normalized
away; the accepted frozen policy enumerates both native parents and all scopes.

Immutable science **442603249**, tag
`participation-ak-senate-native-controls-20261112-01`, contains the full factual
AK original, safe receipt without acquisition headers, entire accepted Senate
identifier packet/all 34,492 rows, all earlier crosschecks, policy, code/tests
and every complete query/result. All **14** full assets were anonymously verified.
The **1,263,132-byte / 21-member ZIP** has SHA-256
`be61d07d9092f87bdc8cfee5e3a7b5e5fc9e4109d1a89da027ae932d54467bcd`.
Inputs/results/acceptance: `data/ak-senate-native-controls/20261112-01/`.
No acquisition, old reduction, model refit, new source count or website build
was repeated. Website `7088482` and its actual Pages acceptance remain unchanged.
This does not resolve Alaska's Nonpartisan House comparison or Maine's House
round hold, and does not promote a new live view.

## 1996 CPS native state participation and response frames

The three original Census P20-504 tables (Internet release August 17, 1998;
November 1996 election) now have a complete maintained reader and immutable
science release **442536397**, tag
`participation-cps-1996-state-points-20261112-01`. Scientific code is
`72ae9ad5cf5effe8c45f7d0464464e9de8f33fed`.
The separately declared native directory and all three TXT files returned 200
and were acquired once; compiled directory HTML is not redistributed.

All **1,923 rows / 19,539 literal cells** are preserved: 1,040 race/origin-by-age,
780 sex-by-age and 103 citizen-gender rows, across 50 states, DC and the US.
All **4,576 metric decisions** retain 4,142 selected source percentages,
96 suppressed `(B)` holds, 20 rounded-zero-base holds and 318 absent
citizen geography/gender decisions. The selections include 520 repeated A/B
totals and 618 citizen-category rates; they are not independent turnout samples.
All 2,600 repeated-total cells match; 1,313 literal integer zeros survive.

A/B use all adults 18+; C uses citizen adults 18+. National reported voting
is **54.2% versus 58.4%**, not one denominator. Counts are rounded thousands,
not sample sizes or exact persons. No sample N, SE or CI is invented. White/
Black and Hispanic overlap; there is no non-Hispanic or API reconstruction.
Fifty-one state citizen-overall cells and two national citizen-gender cells are
not printed and are not fabricated by summing sexes.

The download includes every native cell, all **309 cross-frame count references**,
**206 no/unknown allocation scenarios**, **624 presidential-to-midterm group
decisions**, **104 original/retrospective controls** and **728 same-frame
presidential overall decisions** to 2000/04/08/12/16/20/24, including all holds.
Unknown voting responses are not observed nonvoters; allocation scenarios are
not confidence intervals. Native rounding residuals stay separate, including
the national one-thousand voting residual. No cohort, retention, causal effect,
local allocation or administrative turnout is inferred.

Eight tests, **76,557 independent fixed-column/CSV checks** and two fresh
network/external-command-blocked reproductions match all ten output files.
The complete **1,962,849-byte / 26-member ZIP**, SHA-256
`3a3e5a108d34dda52ebf47ecfe16a4bc746cbbbcc79b459e73d9989be65f4f1f`,
contains all three originals, policy/receipts, the entire accepted 1998 science,
maintained code/tests and every full query/result. All 17 full assets were
anonymously verified. No older acquisition/reduction or NORC refit was repeated.
Inputs and records: `data/participation-cps-1996-state-points/20261112-01/`.
**History integration is verified live** at website
`7088482a2eae2c2da8095ea8f016683983a9058b`, Pages **43164165115**,
artifact **13919427673**. The existing default-closed history view exposes
**520 adult and 103 citizen voting points** using its same 52 geographies,
29 group choices and election-type control. Missing citizen cells stay blank;
voting nonresponse is shown separately. Native White/Black labels now explicitly
span 1996/1998/2002 while old programmatic aliases remain unchanged. No early
point is spliced into the 2006-2024 citizen/MOE chart or a new homepage panel.

Actual production passes all **3,016** new state/group/frame combinations on
desktop and phone, plus no-JS, failed/corrupted and late-response boundaries.
Preserved 1998 **1,508** and 2002 **3,016** combinations pass their complete
six-case production suites. All **3,060** House-map values, **102** real pointer
selections, six dimensions/22 options, both PA scope captions, legacy Senate/
governor values and **48 layouts** also pass. All 69 unqueried production assets
match the actual artifact; all 436 old complete-download pins remain unchanged.
The actual native payload is **996,810,595 bytes** and tar **999,403,520 bytes**,
both strictly below 1,000,000,000. Twenty-two targeted reader tests, Astro
zero errors/warnings (eight pre-existing hints) and the build's four tests pass.
Production history and preserved-map images were inspected. No NORC refit,
new source counts, private respondents or compiled publisher HTML were published.
Records and the two history images are in `website-acceptance.json` and `media/`.

The official Maine results index, 2024 results page and 2026 CD2 tabulation
announcement each returned HTTP 403 on November 12, 2026. All three exact routes
remain stopped, without alternate-client/cache/mirror retries. Unknown denied
body lengths and hashes remain null in `maine-access-holds.json`; no count-stage
compatibility was inferred from candidate totals. Maine's House comparison stays held.

## 2026 Pennsylvania native district control scope

The prior PA hold incorrectly treated blank county-validation joins as missing
native district votes. The accepted county-control query is a UNION of native
reported candidates and county candidate/party keys. Its 18 blank PA entries
are county-validation-only exceptions; all 17 native districts and 34 reported
candidate counts already exist. Every native candidate matches its nonblank
held control exactly, without alias normalization, county summing or zero-fill.
All 18 exceptions are retained, not repaired or deleted.

Reused the complete accepted **1,400-row/435-district/50-state** native candidate
CSV and complete audit at website source **9bf7f3c10f05a311aa96af6b47cc46c2ab3eb68a**,
path `data/county-results/20261107T125502Z/party-votes/`.
The 25,651-byte CSV gzip SHA256 is
`31af5b11d473397ca7928d3f0ef9c455709f0655bf7b2f29cc9ef653d09111f3`.
No acquisition or successful large source parsing campaign was repeated.
The audit explicitly separates provider district/state totals from official
county fragments. Provider totals omit known county-source write-ins; those
are NOT pooled into Other. Current counts remain D2,803,188/R2,142,015/O17,361,
not all Other ballots, certified final totals or participation. All 17 native
source URLs/clocks remain in the full qualification query.

**48 comparable states / AK+ME held.** Only PA is recalculated; 49 states'
numerical fields and complete simulations are reused exactly. PA's reported
known-D/R margin changes from R+2.09314957 to D+13.36998704: +15.46313661 points.
Conditional switching +6.85916448, net participation +8.19411186, Other
+0.09046519 and unresolved +0.31939507 reconcile exactly. Before current-party
conditioning PA projects D+11.15716065, retaining its +2.21282639-point error.
The 48-state preconditioning MAE6.12699827 changes the comparison set, not the
learned source fits or their validation.

Science source **35f6344abf50b4723170bf86221999ea37f726b9**, immutable release
**442474232**, tag `participation-pa-house-native-controls-20261112-01`.
All **18 full assets** anonymously byte/hash verified. Complete
**24,711,519-byte/34-member ZIP**, SHA256
`02f4f6d4b8f6770af5725dd7f0e68752432f772c11d9ca3e4852618b6849b08c`,
contains the entire accepted 47-comparison predecessor, complete native
CSV/audit, source-role query, all eight outputs, 438 assumptions/250 state/
1,500 partition seeds/1,600 group decisions and all sufficient code/tests.
Five new behavior tests, 1,427 independent SQL/native-scope checks and 52,258
independent numerical checks pass. Two fresh network/external-command-blocked
PA-only reproductions under different hash seeds match all eight outputs.
No new private source fits, respondents, fine cells, session headers, compiled
publisher app code, county allocation or population/causal validation.
**Website8f1f4e6 is verified live**, Pages**43152046888**, actual artifact
**13914043283**: **996,798,434 payload / 999,393,280 tar bytes**, both strictly
below1e9. All68 unqueried production assets/436 unchanged full-download pins pass.
Production3060map/group values/102actualpointer clicks/all50summaries/6dimensions/
22options/noJS/fault/checksum/retry/latest-office isolation pass. Both new PA
scope captions are verified/captured, all eight production images inspected.
Preserved Senate/governor1020values/126summaries and48responsive/tab layouts pass.
Full accepted records/media: `data/pa-house-native-controls/20261112-01/`.

## 2026 official House endpoint successor

**Previous 47-comparison increment, preserved unchanged.** PA eligibility is
superseded above; all other numerical state rows and simulation cases remain.

The official House Clerk declaring page links its complete
[2024 congressional statistics PDF](https://clerk.house.gov/member_info/electionInfo/2024/statistics2024.pdf).
Acquired once through the common native intake on November 12 UTC:
608,100 bytes, 87 physical pages, SHA256
`d4ba800fc17135b616ae556c92861080ab962d95916ace34b546c5aac824aec4`.
The HTTP Last-Modified is March 19, 2025, not a separately established publication
date. The compiled declaring-page HTML stays private; its safe receipt is retained.

All 50 states/435 districts, 1,279 candidate-party lines and 68 excluded
noncandidate lines are preserved. Independent pypdf6.16.0 stream-order extraction
matches all 1,347 complete lines/1,345 numeric cells/two footnote-only counts in
8,082 checks. All 459 literal national recap cells remain, including dot/NULL
fields. Candidate votes plus separately excluded accounting reconcile every
printed state parent; blank/overvote/continuing/exhausted quantities are never
added to candidate votes. Explicit same-nominee fusion lines and mixed major-party
affiliations are qualified without inferred coalitions. FL-20/OK-03 `(1)` values
stay NULL; both no-ballot footnotes are independently checked.

The endpoint-only successor changes 21 previously anchored baselines and adds
12 comparisons (CT/HI/IL/IN/LA/MS/NJ/OK/RI/SD/VA/VT). **47 comparisons/three holds**:
AK nonpartisan classification, ME unresolved ranked-choice round compatibility,
PA missing current candidate totals. All held 2026 district controls remain
exactly the accepted **20261107T125502Z** source snapshot, not fresh or certified
final counts. No private survey refit, changed coefficients or local allocation.
Only 33 changed-state cases are recalculated; the other 17 states' numerical
fields and complete simulations are reused. The preconditioning 47-state margin
MAE is **6.21027852 pp**, retained as error rather than a behavioral component.

Source **7d691c95593714ef4e3b251b0d16c63f72a9f6e9**, immutable release **442419209**,
tag `participation-house-clerk-norc-endpoints-20261112-01`.
All **17 full assets** anonymously byte/hash verified. Complete
**21,876,268-byte/32-member ZIP**, SHA256
`fa8f548d131cdd8938d25966ca65888812eca15f800693029a6712f0a4b82cdc`,
contains the entire accepted NORC predecessor, full PDF/native facts/receipts/
endpoint decisions, all eight complete outputs, 432 assumptions, 250 state seeds,
1,500 demographic partition seeds and all sufficient code/tests. Sixteen tests,
52,216 independent numerical checks and two fresh blocked-network/external-command
reproductions pass all eight output bytes. Public simulation reproduction uses
the standard library; optional fresh native extraction declares PDF dependencies.
Source fits, original release and all historical complete downloads remain intact.
**Website 9bf7f3c is verified live**, Pages **43141953120**, actual artifact
**13910840679**: **996,797,587 payload / 999,393,280 tar bytes**, both strictly
below 1e9. All 68 exact unqueried production assets and 436 unchanged full-download
pins pass. Production checks verify 3,060 state/view/group values, 102 actual
pointer selections, all 50 summaries, six dimensions/22 options, no-JS and
failure/checksum/retry/latest-office isolation. Preserved Senate/governor views
pass 1,020 values/126 summaries; 48 responsive/tab layouts pass. All six actual
production images were visually inspected. Full records/media:
`data/house-clerk-norc-endpoints/20261112-01/`.

## 2026 NORC-informed demographic House transitions

**Original November 11 version, preserved unchanged.** The endpoint-only successor
above supersedes its return counts and observed-comparison coverage, not its
learned source models or validation scores.

The user rejected bounds-only and count-only substitutes for the requested
explanatory model. New science learns demographic/prior-choice associations from
**113,020 CHEP2026** and **136,435 AP/NORC2024 positive-state-weight cases**.
Actual joint demographic records are used privately; the old statewide synthetic
coupling and products of separate demographic marginals are not the fitted input.
An explicit AP2024 President/House bridge supplies latent House24 because CHEP
recalls President24, not House24. Actual recalled House22 is used in both studies;
forced-choice QVOTE2022S is excluded and the reversed AP/CHEP party codes handled.

All **50 source states / 35 same-office endpoint reconstructions / 15 source-only
scenarios** retain DRONU, six separate demographic partitions, all **1,600 group
decisions**, **360 assumption cases**, **250 state seed cases** and **1,500
demographic partition seed cases**. Switching, exit, entry/return, Other and
unresolved contributions use exact symmetric margin accounting; net participation
is entry plus exit. Denominator effects belong inside each mechanism. Demographic
dimensions overlap and are not additive causes. Source disclosure holds remain.

Source training excludes current partisan returns. Respondent holdout log loss
improves **0.54790594 to 0.47895891** with demographics. The House24 bridge has
slightly improved log loss but **slightly worse Brier**. Untouched AP2022-to2024
response transfer improves only modestly (**0.74408945 to 0.74173593**).
Before current-party conditioning, the 35-state margin MAE is **5.98790598 pp**;
all prediction gaps remain model error, not another behavioral residual.
Return matching is a separate conditional reconstruction, not validation.
Full scores, formulas, source definitions and limitations:
[NORC House methods](docs/NORC_HOUSE_TRANSITIONS.md).

Scientific source **8f74ee8e4521d21142e8ee275cc154cb2bbfbd80**, immutable release
**442345226**, tag `participation-norc-house-demographic-20261111-01`.
All **16 full assets** anonymously byte/hash verified. Complete
**17,856,244-byte / 21-member ZIP**, SHA256
`8ec723e49df49af59b559d4835cf7846e70ac46e4e28bac7b5c2fe0a67bc7ae0`,
contains all permitted fitted synthetic priors, eight complete outputs/every
query, code/tests/checks and the entire accepted return-source predecessor.
Nine focused tests, **51,712 independent checks** and two fresh blocked-network/
external-command reproductions match all eight outputs. Public simulation
reproduction is complete; private training requires original local files.
No raw respondents, identifiers or private fine source cells are redistributed.

**Original website aef5122 was verified live**, Pages **43130276092**, actual artifact
**13904749933**. Actual payload **996,845,969** and tar **999,434,240** bytes
both pass the unchanged strict 1e9 limits. All **68 exact unqueried assets** and
**436 unchanged complete-download pins** pass. Production checks match
**3,060 new state/view/group values**, all 50 summaries, 22 options across six
demographic dimensions and **102 actual phone/desktop pointer selections**,
including tiny D.C. A generic invisible hit area and correct paint order improve
selection without changing displayed geometry. No-JS, failure/checksum/retry,
late-office isolation, 1,020 preserved Senate/governor values/126 summaries and
48 responsive/tab layouts pass. All six production screenshots were inspected.
Original 113 models and 113 archived return-constrained decisions remain complete.
Acceptance and media: `data/norc-house-demographic/20261111-01/`.

The existing single map has observed, switching, net participation, entry, exit,
Other, unresolved and retained-share options with state/group controls and
saved no-JS state summaries. All old models/downloads remain. Modeled absence is
not confirmed staying home; entry/return is not proven first-ever voting.
Frame size/latent affinity, residence/age/candidate availability/source-weight
and reporting scope remain assumptions. No county/precinct allocation or new CI.

## 2026 aggregate-compatible gross-flow bounds

The return-constrained split is not identified by the observed endpoints. New
constraint-only calculations retain all **113 decisions / 89 comparable cases /
24 unavailable** and compute **356 explicitly conditioned accounting frames**:
the three already-declared common-frame sizes plus a separately labeled
large-frame mathematical counterexample. There is **no new partisan fitting**.
All **89 central frames allow zero D/R switching**; all 89 gross-switching ranges
are nondegenerate. The fitted switching contribution is therefore an assumption,
not a quantity required by those aggregate returns.

All **1,912 sharp metric bounds / 224 explicit holds / 3,824 extremal tables**
include exact source endpoints and dual cut certificates. Independent verification
passes **930,069 exact checks / 806,912 network-cut evaluations**, with eight
focused tests and two fresh offline reproductions of all **six full outputs**.
No accepted source reduction or fitted simulation is repeated. Other supplied at
both endpoints uses DRON; D/R-only governor frames use an **opaque X**, not zero
Other or measured nonvote. Separate Other/no-contest-vote bounds stay unavailable.
Entry into D/R can include prior Other choices; it is not first-ever voting.

These are continuous accounting-unit bounds **conditional on an assumed frame**,
not measured people, eligible population, confidence intervals, no-ballot histories
or net-margin contribution intervals. Separate extrema are not jointly attainable
partitions. A separately labeled large frame admits one zero-retention AND
zero-switching table for every case while preserving all recorded endpoints;
that construction is not an additional fitted estimate or an observed history.

Scientific source **5402033954fd94a5f99ee4e244545ed7cdb6994e**, immutable release
**442279581**, tag `participation-flow-identification-20261111-01`. The full
**15,444,633-byte / 15-member ZIP**, SHA256
`93a5c627f54509d2002b80524a763cc059a96601013d62fad65f0866e9e5464f`,
includes the **entire 14,943,668-byte accepted predecessor**, complete sufficient
inputs/code/tests, every query/witness/constraint/certificate and the exact viewer.
All **13 full release assets** were anonymously verified byte-for-byte; no
metadata-only substitution. Records: `data/flow-identification/20261111-01/`.

Website **156bfa8 is verified live**: Pages **43117213469**, actual artifact
**13898329284**, successful full build and exact copied-source credential guard.
Actual **996,785,099 payload / 999,372,800 tar bytes** both pass the strict
1,000,000,000-byte limit. All **67 checked unqueried production assets** match
the actual artifact; all **436 complete-download pins** remain unchanged.
Independent live browser **43117281181** checks **1,530 state/view values /
226 state/office summaries**, all 113 saved gross-bound decisions, pointer and
persistent selection, missing cases, no overflow and the actual no-JavaScript
table. The exact artifact/production checker **43118691759** also passes.
All original 113 model objects, 113 constrained decisions, source counts,
geometry and other catalog datasets are preserved. No new panel or map.

Twenty reader tests and Astro checks pass. Local chart export hit ENOSPC;
CI completed the full build, browser and artifact checks on separate storage.
The first temporary artifact checker had a quoting error; it was corrected and
checked the SAME uploaded artifact, without another site build or old-model fit.
Verification workflows remain branch-only, not production YAML changes.
Complete production/browser records and screenshots are retained here. The
canonical local owned-document and session-SQL sync remains blocked by ENOSPC;
these current remote records supersede stale local progress. Do not repeat this
accepted science/build/validation when storage recovers; only finish that sync.

## 2026 both-endpoint return-constrained transition scenarios

The previous live equation was **not a useful explanation of reported swing**:
it joined a recalled-presidential survey-frame contrast to observed same-office
returns, then called the difference Other/unallocated. Texas's 22.41-point
bucket included 14.62 points of prior-baseline mismatch and additional entry,
other-choice, unresolved and denominator terms. This was an **atlas-wide
architecture issue**, not a Texas-specific arithmetic bug.

Scientific source **07fee19a4e4130cf3603635e90af36faa0c26a0d** now implements a
different model: a nonnegative synthetic transition table constrained to **both
recorded D/R candidate-vote endpoints** in the qualified same-office frame.
There are **113 complete state/office decisions, 89 fitted comparisons and 24
explicitly unavailable comparisons**: 35 House state aggregates, 26 Senate
comparisons and 28 governor source frames are fitted. Missing comparisons do
not become zero contributions or borrow another state's baseline.

The accepted state-specific synthetic survey/recalled-president associations
are a **prior only**, not the previous same-office result. Relative-entropy
row/column scaling chooses a feasible table. Four Shapley mechanisms—major-party
switching, no current-contest vote, entry/return, and Other-party choice—include
denominator effects and exactly reconcile the normalized D-R margin. There is
no ad-hoc return/frame balancing term. Gross retention/switching/outside/Other
shares partition the modeled previous major-party frame, not all voters.

**Fitting is not independent validation or identification of individual histories.**
The common candidate-vote accounting-frame size is assumed from the prior's
known-party weight, not a measured eligible population. The nine cases vary
persistence **0.5/1/2 times** the accepted factor and frame size **0.8/1/1.25**;
lower frame bounds remain explicit. Ranges are assumption sensitivity, not
confidence or identification intervals. No counted vote for the target office
does not identify no ballot, first-ever voting, eligibility, death or migration.
Original synthetic N/U categories are pooled only in the prior; no source
observations are recoded. No state model is allocated to counties or precincts.

Actual Other counts constrain endpoints where supplied. The governor source
frames supply D/R only: their raw Other counts remain absent, **not zero**;
the model's Other/outside split is explicitly prior-assumed. Changed competition,
partial reporting, native source clocks and geographic/source-frame qualifications
remain in every return comparison. This model does not certify full-election
turnout or independently validate any behavioral mechanism.

All **801 fitted cases / 12,816 synthetic cells / 678 endpoint decisions / 113
selection decisions** are available. An independent verifier checks all native
counts/both margins and evaluates every contribution through all **24 mechanism
orderings**: **119,478 checks** pass. Five mathematical regression tests and two
fresh network/external-command-blocked reproductions pass all **six full query
output bytes**; the accepted older source simulations are not rerun.

Immutable science **442171871**, tag
`participation-return-constrained-20261111-01`, supplies a complete
**14,943,668-byte / 17-member ZIP**, SHA
`2377ea253d33b88af3146bad4e2a52c9936d97b178c00a4fa0e3be022aadeae1`.
It includes both **entire** accepted scientific predecessors (9,977,891 and
4,307,149 bytes), all return comparisons, new code/tests, complete queries,
viewer and results, never metadata-only links. All **13 assets** were verified
as full anonymous bytes. Reference byte reproduction uses Python 3.9; later
versions can differ in floating summation/serialization.
[Complete model and queries](https://github.com/hanshanley/margin_of_error/releases/download/participation-return-constrained-20261111-01/complete-analysis.zip).

Website revision **442287da1524ccf8397d536861918e0ff5bb75b7** integrates these
scenarios into the existing single map with switching, no-contest-vote,
entry/return and Other-choice views. The original 113 estimates remain archived,
not presented as the observed swing decomposition. All 113 new decisions also
have a server-rendered table and sum-preserving display rounding. Local real
desktop/phone tests check **1,530 state/view values and 226 state/office
summaries**, selection and unavailable cases, without valid-data overrides.
Eighteen reader tests, Astro checks/build and both responsive screenshots pass.
**Production acceptance passed November 11 at 21:57 UTC.** Fresh Pages run
**43106318180** successfully built and deployed the unchanged revision;
artifact **13893564445** contains **996,768,461 payload / 999,362,560 tar
bytes**, both below the strict 1,000,000,000-byte limit. All **67 checked
unqueried live assets** match actual CI artifact hashes, and the original
**436 complete-download pins** remain byte-identical. The exact copied-source
credential guard passed in build job **130810475808**.
Actual production desktop/phone checks pass all **1,530 state/view values /
226 state/office summaries**, pointer and persistent selection, unavailable
states, shared signed scale and no horizontal overflow or valid-data overrides.
Both responsive screenshots were inspected. Full embedded-data comparison
confirms all **113 original model objects** and the complete **113 new
decisions** remain exact, with both server-rendered tables present.

The earlier `startup_failure`/zero-job incidents are preserved in the
pending/recovery/blocker records. Bounded isolated standard/max-queue controls
**43105585347 / 43105585333** both succeeded before the fresh dispatch.
No diagnostic workflows were merged into main and no production YAML or
numerical model changed during recovery. This establishes operational recovery,
not the internal cause of GitHub's initial failures. The new
`actions-startup-diagnostic.json`, `website-acceptance.json` and
`production-acceptance.json` retain full controls, browser results and actual
artifact/live hashes. No accepted source reductions or fits were repeated.

Records: `data/return-constrained/20261111-01/`. Counts, native geometry,
resident context and the separate original survey-frame scenario dataset are
unchanged. This completes a coherent **conditional model/display correction**,
not identification of actual staying home or nationwide administrative histories.

## 2026 Louisiana source-native early group counts and compositions

The newly acquired official **Statewide Early Voting Statistical Report**
supplies **64 parish rows plus a separate state parent / 1,040 literal count
cells** across two full pages. Native **VOTES 536,190 = INPER 448,588 +
ABS 87,602**. These are counts in this source-defined early/absentee report,
**not complete-election ballots or independently verified unique people**.
The source's ABS is not relabeled into mail-returned activity, and source
parish codes 01-64 are not inferred FIPS or approved map references.

The state parent's native race margins are **WHITE 328,590 / BLACK 184,348 /
OTHER 23,252**. Native sex margins **MALE 224,376 / FEMALE 311,536** leave
**278 arithmetic units** outside those two printed fields. All **37 parish
sex residuals** and **21 literal zero count cells** remain. The residual is
not normalized away or identified as a new sex/nonvoter category. Race,
affiliation and INPER/ABS margins sum to native VOTES; all **16 same-report
parish-column sums** equal their printed state parents. Parent and children
are repeated margins, not 65 independent populations or additive votes.

All **455 race/sex/native-method composition rows**, **260 margin accounts**,
**130 opaque-subset decisions**, 16 parent controls and **51 state/DC coverage
decisions** are complete. Fifty states are not supplied by this Louisiana
source, not zero or globally absent. Composition percentages use **own native
VOTES**, not a classified-sex subtotal or registrations. Exact decimal shares
are arithmetic, not sampling precision or confidence intervals.
Registration denominators, group turnout, full-election ballots, unique
people, sampling N, CIs, race-sex-method joints, measured staying home and
eligibility/deaths/migration remain null. Native racial labels are not CPS,
SSRS or resident-profile aliases. Party fields are registration accounting,
not choices; no partisan-choice shares are derived. UOCAVA IN/OUT and ASST D/I
stay literal without inferred definitions, disjoint unions or intersections.

The report labels election **November 3, 2026**, query begin **January 1, 1900**,
query end **November 9, 2026**, and print **November 10, 2026, 3:10:06 AM**.
Printed timezone is unknown. The PDF's separate creation metadata is not
used to fill that clock's timezone. The 1900 filter bound is not an observed
voting start; no finality, certification or complete-count claim follows.

Scientific source **9ba392d92277933786baeab6755c7cdddfaafe71** and immutable
science **442055936**, tag `participation-louisiana-early-groups-20261111-01`,
publish all **16 full assets**, anonymously byte/hash verified. The
**262,124-byte / 27-member** ZIP has SHA256
`f788b1d388d52efbba78121513cd16c82445c2ad4acd89fb8f9bb44379708bfe`.
It includes the complete **157,893-byte** original PDF, full cached text,
all native facts and independent pypdf-coordinate evidence, policy/provenance/
access holds, maintained code/tests, the **910,047-byte** result and every
complete query. This is a standalone new source, not a replacement or
repackaging of older accepted science. Publisher HTML/apps/session headers,
private voter/survey records and identifiers are not included.

All **1,040 original cells** match a second PDF engine. Seven focused tests,
**8,072 independent checks** and two fresh warning-fatal network/external-
command-blocked reproductions pass every full result/query byte. The installed
native C reader failed; the independent audit succeeded with the already
installed pure-Python pypdf reader, without source changes or a native-data
shortcut. No earlier successful acquisition or scientific reduction was repeated.
Inputs and records: `data/participation-louisiana-early-groups/20261111-01/`.
Website **84ce048**, catalog **a1e3cb15** and accepted models are unchanged;
zero new builds or data activation. Frame/method/reference qualification is
still required before any mapped integration.

The separately discovered Michigan general-election registration/turnout PDF
returned **HTTP403 / 537 bytes**, SHA256
`e4191d850748db7a004ddfaadfafd6fab7bb89d5276065b7bde803d8816db5f1`.
It stays stopped with no alternate client, cache, mirror or web-snippet counts.
The older Michigan statistics index/dashboard were not retried, and Louisiana's
unresolved registration hostname was not guessed or retried.

## 1998 points in the existing historical view

The qualified 1998 voting points are now **verified live**, alongside the
unchanged 2002 points, inside the existing default-closed **Source studies &
supporting analyses → Historical participation and demographic comparisons**
section. No new homepage panel or tab is added. The same state/group controls
expose **355 available 1998 voting points** across the 52 geography choices.
The source is checksum-pinned and lazy until the history details open.
Its full result SHA256 remains
`0b1e80744e3a24145aa2494c3581e602b458cb3330806d64f8757a32ab4c6a19`.

The 1998 row uses **source adults 18+**, never citizen turnout. Its directly
printed SE is labeled as an SE, **not a 90% margin**. Source suppression stays
unavailable; no point or uncertainty is reconstructed. Four compatible older
labels explicitly say 1998/2002, while old 2002 programmatic aliases remain
supported. A separate 1998 non-Hispanic Asian/Pacific Islander option never
aliases the broader 2002 API or modern race-alone categories.
Neither early all-adult row connects to the citizen chart. The separate 2002
citizen-overall row, all **642** selected distinct 2002 points and their
unqualified workbook margins remain unchanged.

Website **84ce048728f9e159db9798f634c07fff8a0c92cc**, sole Pages
**43063989329**, main guard **43063989413**, and artifact **13874379278** pass
actual **996,331,113 payload / 998,922,240 tar bytes**, both strictly below 1e9.
All **66** checked unqueried production assets match the exact native artifact,
and all **436** old complete-download pins remain unchanged. Two new links
reuse the existing full 1998 science ZIP and all-1,404-metric CSV; no new
source acquisition, scientific reduction or package publication was repeated.

Six new reader tests, five preserved 2002 reader tests and 23 existing guards
pass, as do Astro check and the full build. Actual desktop/phone acceptance
checks **1,508** 1998 selections and **3,016** preserved 2002 selections per
screen across **52 geographies / 29 options**. All old **13,156** history cells,
**6,788** plotted points and **1,441** gap-safe segments per screen pass.
No-JavaScript, failed/corrupt source, late-response selection isolation and
overflow checks pass with no valid-data overrides or browser errors.
All **113** model objects/saved rows and all four checksum-checked catalog
readers remain intact; catalog **a1e3cb15** and geometry/count/scenario datasets
are unchanged. Desktop and phone production layouts were visually inspected.
Records: `data/participation-access/20261111-cps-1998-history-ui-01/`.

## 1998 CPS native state demographic points and midterm snapshots

The newly acquired Census Table 4 TXT supplies **468 native rows / 4,680
literal metric cells**, nine native groups in **all 50 states, D.C. and the
United States**. The complete **1,404 metric decisions** select **1,060 reported
points**: **711 registration/voting percentages** and **349 separate citizenship
shares**. Registration and voting percentages use the **source adult 18+
population**, not citizen adults; citizenship share is not turnout or eligibility.
Counts are rounded thousands, not sample sizes or exact persons.

The table's explicit Standard error headers qualify **1,059 directly printed
source SEs**, including ten literal zeros, not new confidence intervals.
All **343 `(B)` measures** remain suppressed and **32 literal dot counts** remain
unqualified symbols, never missing-as-zero; **14 actual zero counts** survive.
New Jersey male citizenship percentage **`900.`** is not repaired to 90.
New Mexico's citizenship SE **`0.8.`** stays malformed while its valid 93.5%
point remains available. Selection is metric-specific: a withheld citizenship
share or SE does not erase the same row's valid participation measures.
No sample-N, precision certification, suppressed percentage reconstruction,
derived citizen turnout, new interval or source correction is introduced.

Native categories remain literal and overlapping: Total, Male, Female,
N-H White, N-H Black, N-H API, Hispanic, White and Black. Source footnotes define
N-H as Non-Hispanic, API as Asian and Pacific Islander, and Hispanic as any race.
The complete **936** 1998-to-2002 group/metric decisions retain **675 compatible
native-label descriptive snapshots**, **104 non-Hispanic-API versus all-API
holds**, 147 native 1998 metric holds and ten accepted 2002 selection holds.
The broader 2002 API category never substitutes for 1998 N-H API. These are not
modern race aliases, harmonized population definitions, individual retention,
observed staying home, significant changes or demographic histories.
1998 printed SEs do not interpret 2002 confidence scalars or qualify change CIs.

All **104** original-versus-retrospective decisions retain **102 matching
state percentages** and two absent national endpoints: common-source
corroboration, not independent administrative validation. All **208**
2018/2022 same-VAP overall decisions retain **204 descriptive differences**
and four absent national endpoints. Unknown eligibility/deaths/migration and
local allocations stay null/unqualified; no accepted model or live UI changes.

The ordinary Census landing-page GET returned **403 / 17 bytes** and remains
stopped. A **distinct native-file directory** returned 200, explicitly listed
`tab04.txt`, and its separately acquired original returned 200 / **70,868 bytes**,
SHA256 `bc998b4ac2db5c65b2aa55839df907c70d599eddeca0f988500ef80339095833`.
This is not a cache/mirror/client recovery of the denied HTML page. The native
Internet release date is **July 19, 2000**; the indexed report date is separate.
No successful old acquisition, parser or numerical reduction was repeated.

Scientific source **f6c42915614ca585e1cc875b49af9fedf1432986** and immutable
science **441905879**, tag `participation-cps-1998-state-points-20261111-01`,
publish all **13 full assets**, anonymously byte/hash verified. The
**1,408,974-byte / 19-member** ZIP has SHA256
`c94bc51267849010ea393af44cb2dd3da7a507e86f45d8dfdd796033c8939a8b`.
It includes the complete original TXT, all permitted policy/provenance, the
entire **1,241,697-byte** accepted 2002 predecessor with its full XLS/PDFs and
older science, maintained code/tests, the **2,820,598-byte** result and every
complete query. Seven tests, **37,044 independent checks** and two fresh
warning-fatal network/external-command-blocked reproductions pass all output
bytes. Native original whitespace is retained, not reformatted.
Inputs and records: `data/participation-cps-1998-state-points/20261111-01/`.
At scientific publication, website **c1357ec** and catalog **a1e3cb15** were
unchanged with zero new builds. The separately tested presentation is above.

Separately, the bounded primary SSRS/AP route review still does not resolve
the actual race/ethnicity question, Hispanic priority, multiracial/nonresponse
coding or historical CES compatibility. This does not claim global absence
of a questionnaire. CNN/NBC web robots denials stay stopped. Held methods and
the old private 12-row diagnostics were not reacquired/recomputed, and no new
demographic residual is qualified. The distinct Census calculation above does
not harmonize SSRS/CES groups. Record:
`data/participation-cps-1998-state-points/20261111-01/source-qualification.json`.

## 2026 MEVP direct state participant history and experiences

The already-held November 7 national crosstabs from the **BSP Research /
African American Research Collaborative 2026 Midterm Election Voter Poll**
contain actual state columns, not just national marginals. Their first panels
now supply **11 direct state/group profiles**, five national group references,
all **51 source-column decisions** and **663 independently checked numerical
facts**. The complete **255 state/DC-by-five-group query** retains **244 missing
combinations**; no national percentages are allocated to missing states.
The 35 multistate/partisan context columns remain in the factual inventory,
excluded from state/national profile selection.

| Study-native group | Direct state columns (raw respondent N) |
|---|---|
| Latina/o | AZ 337; CA 421; FL 516; MI 241; TX 844 |
| Asian American | CA 389; TX 283 |
| White, non-Hispanic | MI 441; TX 448 |
| African American | MI 314; TX 443 |
| Native American | No explicit state columns in these held panels |

These are source-defined participant/intender compositions, **not population
turnout**. Screening includes reported early voters **and respondents certain
they would vote on Election Day**; completed voting is not independently
verified. The PDF field dates are October 19-November 2, while the held methods
end November 3; both definitions remain visible. Q1 asks first **November
general-election** history, not first-ever voting, first eligibility, measured
retention or individual transitions. Its native bins are 2026, 2024, 2022 and
2020-or-earlier; unoffered years are not silently added.

Printed 99/101 totals, prior-bin sums and signed `100 - printed total` residuals
remain literal. For example, the national Latina/o prior-bin sum is **84%**,
not the 83% complement of the printed 17% first-2026 share. The -1-point residual
is unresolved rounding/response, not an observed nonvoter class. Q2's eight
experience responses remain **multiresponse**; no disjoint total, any-problem
union or counts from N times percentages are inferred. Raw N and the minimum
100-respondent diagnostic are not weighted population, effective N or precision
certification. Whole-group margins do not qualify state-column intervals.
State-versus-own-national differences are nested common-source descriptions,
not independent replications. Study-native groups are not harmonized to CPS,
CES or other survey race definitions; eligibility, deaths, migration, population
turnout/absence, first-ever voting, individual retention and design intervals
remain null. No live model calibration, local allocation or frontend activation.

The newly declared AZ/FL/TX PDF routes and their three separate press-release
routes each returned **HTTP403, 17 bytes**, SHA256
`2938e9f1284180959e33ab1718d0793a72ff6e4cdb8108c34dcd14e69446de5c`.
All six routes are stopped without retries, alternate clients, caches or mirrors.
Discovery does not count as original acquisition. The state values above come
only from distinct national originals already held on November 7; no blocked
state original was recovered or reconstructed.

Scientific source **006563f6acc5c7b4f227947a5796b107e90dd3e9** and immutable
science **441835842**, tag `participation-mevp-state-profiles-20261111-01`,
publish all **12 full assets**, anonymously byte/hash verified. The
**53,385-byte / 22-member** complete ZIP has SHA256
`8943fc1bf7ff07be11c4f847f4a31dc058f9fe696cc1c1c5a65ff44e897bb4d7`.
It includes every permitted sufficient numerical fact, methods/policy/access
decision, the entire accepted predecessor science ZIP, maintained code/tests,
full results and every query. Copyrighted originals/prose/HTML/session headers
are not redistributed. Seven focused tests, **1,962 independent checks** and
two fresh warning-fatal network/external-command-blocked reproductions pass
every full result/query byte. Original acquisition and earlier joint reductions
were not repeated. The live website **c1357ec**, catalog **a1e3cb15** and accepted
model outputs are unchanged; no website build was needed.

Inputs: `data/participation-mevp-state-participation/20261111-01/`.
Results/publication/acceptance:
`data/participation-mevp-state-profiles/20261111-01/`.

## 2002 CPS points in the existing historical view

The point-only science below now has a separately qualified presentation in the
existing **Source studies & supporting analyses → Historical participation and
demographic comparisons** section. Both details stay closed by default.
No new homepage panel or tab is added. The 2002 source loads only when the
historical details open, from the exact immutable research result with SHA256
`9d9fe04a02ca1aec9563699d4145e6657777cb01d3af0dbfec69ecf85df0de2d`.

The geography/group controls expose two separate 2002 population rows:
**all adults 18+** and **citizen adults, overall only**. All source holds remain
unavailable, not zero. Five old racial categories have explicit 2002 labels
instead of being aliased into race-alone or race-in-combination categories.
No workbook margin is inferred and no 2002 all-adult point is connected to
the citizen-series chart. The original **13,156** query cells, published margins,
gap-safe lines, 2004 baseline, source tables and full downloads are unchanged.

Website **c1357ec** is **verified live**. Sole Pages **43030652407**, main guard
**43030652544**, and artifact **13861735166** pass actual
**996,321,829 payload / 998,912,000 tar bytes**, both strictly below 1e9.
All **65** checked unqueried production assets match the native artifact,
and all **436** old complete-download pins remain unchanged. The existing
immutable 2002 ZIP and complete 832-row CSV are linked; no scientific packet
or source acquisition was repeated for this presentation.

Five focused reader tests, six source-guard tests, Astro check/full build and
actual prepared-site/production browser tests pass. Each desktop/phone run
checks **2,912** point-selection cells across **52** geographies / **28** options,
retaining **642** selected distinct source points. All old **13,156** history
cells, **6,788** plotted points and **1,441** gap-safe segments per screen pass.
No-JavaScript, failed/corrupt source, late-response selection isolation and
overflow checks pass with no valid-data overrides or browser errors.
All **113** original model objects/saved rows and all four catalog readers
remain intact; catalog **a1e3cb15** and geometry/count/scenario datasets are
unchanged. No new uncertainty, 2026 estimate or local demographic rate is added.
Records: `data/participation-access/20261111-cps-2002-history-ui-01/`.

## 2002 CPS reported points and midterm snapshot comparisons

The already-held 2002 Census voting/registration workbooks now have a maintained
**reported-point-only** public selection. All **832 native rows / 8,320 metric
cells** remain available. **693 source table rows** are selected, representing
**642 distinct geography/frame/category cells**, including **540 non-total
group rows**. Repeated total rows and overlapping groups are not independent
or additive estimates. No raw survey microdata or voter identifiers are used.

Table 4a sex/race/Hispanic-origin and Table 4b age percentages use **all adults
18+**, not citizen adults. Only Table 4c's separate overall percentages use
**citizen adults**. Exact native White, Non-Hispanic White, Black, Non-Hispanic
Black, Asian and Pacific Islander, and Hispanic-of-any-race labels are retained.
They are not harmonized modern race categories or exclusive demographic
partitions. All **139 held rows** remain withheld, not repaired or reconstructed:
**131** missing/suppressed, five other inconsistent rows and **three Pennsylvania
conflicting totals**. One Pennsylvania total also has a native defect, making
**six flagged defect rows** in all. The national Non-Hispanic White source population discrepancy
is preserved despite the separate report's different printed value.

The public selection resolves the earlier all-or-nothing publication hold by
publishing **reported points without interpreting unqualified precision**.
The source's 75,000-person caution uses weighted population, not sample size
or a precision guarantee. Native confidence scalars remain literal; no new
standard errors, confidence intervals, significance tests or change intervals
are constructed. Only the directly printed national citizen interval is
retained as a report fact. The prior factual/method reviews are unchanged and
**workbook-wide precision mapping remains unqualified**.

All **832 source-reconciliation decisions** are included. The **150** supported
overall-table comparisons match both the reported voting and registration
percentages in the held retrospective series. This is common-source
corroboration, not independent administrative validation. There are **104**
complete 2002-to-2018/2022 midterm citizen-overall snapshot decisions:
**100** arithmetic comparisons across 50 state/D.C. jurisdictions, two
Pennsylvania source holds and two absent national retrospective endpoints.
Population controls/definitions are not declared harmonized, and the changes
are not fixed-person retention, administrative staying home or 2026 estimates.
No state/group result is allocated to counties or precincts.

Maintained scientific source **fe8933c** includes the selector, independent
verifier, complete-query packager/reproducer, tests and sufficient frozen
inputs. A CSV JSON-roundtrip column-order defect was caught before science
publication and fixed with a focused byte-identity regression; values did
not change. **Ten tests / 24,438 independent checks** and two fresh
warning-fatal network/external-command-blocked reproductions pass every full
result/query byte. Accepted native parsing, acquisitions and prior reductions
were reused, not repeated.

Immutable science **441661238**, tag
`participation-cps-2002-reported-points-20261111-01`, has all **12 full assets**
anonymously byte/hash verified. Its **1,241,697-byte / 25-member**
[complete packet](https://github.com/hanshanley/margin_of_error/releases/download/participation-cps-2002-reported-points-20261111-01/complete-analysis.zip)
contains all three original XLS files, both full official PDFs, complete
accepted factual/methodological reductions, the **entire 368,608-byte**
accepted historical state-frame science ZIP, maintained code/tests, complete
queries and the full **1,963,519-byte** result. SHA256:
`4d651c36c02a8dd5b413897deccad01d8b2ee05f1f08b9ce2cd068b167858a8b`.
Acquisition session headers and source-page HTML are excluded.
Research records: `data/participation-cps-2002/20261111-01/`.
No frontend/data activation, new panel or website build is part of this increment;
the accepted website, data catalog and prior downloads remain unchanged.

## 2026 Utah four native county count successors

Four already-held November 10 reports explicitly supply **Ballots Cast - Total**:
Piute **737**, Kane **3,395**, Millard **4,149**, and Cache **42,549** for the
November 3, 2026 general election. These are native ballot totals, not candidate
selections, inferred processing subtotals or verified unique people. All seven
successful PDF/XLSX originals were reused; no report was reacquired. The denied
Cache workbook route remains stopped. Its distinct, already-held summary PDF
provides the explicit count; its contest accounting is corroboration only.

The full factual input preserves native aggregate cells, blank versus zero,
Excel errors/formula strings, duplicated field identifiers, clocks and source
qualifications. Independent raw-OOXML/openpyxl comparison agrees on **487 cells**.
The image-only Piute/Kane summary facts were visually checked against the
originals; Piute's OCR errors in completeness/percentage were corrected against
the image, not by altering source facts. Unused certification identities and
source presentation are excluded. Native registrations/printed percentages
remain factual context, not new denominators or analysis rates. The three
workbooks define active registrations as the Friday-before-election reference.
Local OFFICIAL labels do not establish state-level official status or completed
counting; native report times have no supplied timezone.

Factual source **68c22a9** and generic compiler/reference source **ffab1d9** add
only four explicitly hash-pinned missing-count successors. All **147** archived
Utah source observations are retained, with **151** after extension. Each of the
four selected official/context modes still contains **29** county rows:
**23 known counts / six unresolved counts**, retaining the previous 19 counts
and 18 analysis rates. Early/mail frames and other-state/runtime files are
preserved. The same 29-feature **2024** contextual county geometry is retained
byte-for-byte, including its existing overlaps. No 2026 election-boundary,
precinct allocation, statewide total or individual-history claim is added.

Immutable science **441593451**, tag
`participation-utah-count-successors-20261111-01`, has all **12 full assets**
anonymously byte/hash verified. The **232,295,601-byte / 266-member**
[complete packet](https://github.com/hanshanley/margin_of_error/releases/download/participation-utah-count-successors-20261111-01/complete-analysis.zip)
contains the **entire 163,001,209-byte accepted predecessor archive**, all new
sufficient facts, maintained code/tests, complete 29-county/151-history/174-mode
and 29-reference queries, and both full runtimes. Archive SHA256:
`9e753a4f8b363713f9752ba4448993250d9e49eaff68b196b20f0d72cc42e285`.
Two fresh warning-fatal reproductions block network/Node child commands, pass
all **22 tests / 929 independent checks**, and reproduce every runtime/query
byte without reacquiring sources or repeating accepted predecessor reductions.

Native **67d36be3** activates first, staged **383db69b** / catalog **aaff09cd**;
counts **d6308370** follow, staged **b86b45b7** / final catalog **a1e3cb15**.
All **31 Native / 54 count files**, both catalogs and complete-download pins
were anonymously verified after the real frontend schema preflight.
Production uses unchanged website **78df729**, with no new UI build.
Actual desktop/phone acceptance covers all four modes, all 29 count/rate
attributes and **80 real county-pointer cases**, including every unresolved
county. Clocks, hover details, download links, nulls and all **113** original
model objects/saved rows pass with no browser errors or overflow.

Six selected county counts remain unresolved: Daggett, Garfield, Iron, Morgan,
San Juan and Wasatch. They remain gray/missing, not zero. This completes only
the bounded four-county increment, not nationwide/native/precinct coverage.
Research records: `data/participation-count-successors/20261111-ut-01/`
(`observations.json`, `publication.json`, `website-acceptance.json`).

## Demographic and geographic adaptive persistence: negative result

The new cached-input experiment tests five fixed candidate models of gross
switching: global persistence, modeled-nonvoter share, nonvoter plus age,
nonvoter plus rurality, and the primary nonvoter-plus-age-plus-rurality model.
Age is the disclosed 30-49 minus 65+ modeled-nonvoter contrast; rurality is the
disclosed rural-county minus urban-county contrast. Neither is an observed
individual history, administrative turnout or a demographic party association.
The complete official Census region PDF and source pin are retained.

All offices for each held-out state are excluded together. Nested training-only
state tuning operates inside 39 state and four Census-region outer holdouts,
using penalties 0.1/1/10/100 and at least eight eligible training states.
The **215 outer folds / 550 model-table-block predictions** retain every inner
fit, parameter, candidate score, training inventory and exact cached analytic
output. All 55 original current-voter tables in 39 states remain the benchmark;
they are not 550 independent source observations. No original entropy fit or
seed simulation is repeated and no partisan direction/return count is fitted.

**The primary demographic/geographic candidate does not improve the baseline.**
Its table-weighted MAE ties the global model at **1.386175 pp** on state holdouts
and worsens to **1.403362 pp** on region holdouts. State-balanced MAE ties at
**1.383259 pp** and worsens to **1.407497 pp**, respectively. Tuning uses
state-balanced squared error; both error definitions are included in full.
Only **14/39** benchmark states jointly disclose both contrasts. The primary
state test changes no selected grid factor; 25 states use missing-feature
fallback. Region holdouts have six adaptive states, 16 insufficient-training
fallbacks and 17 missing-feature fallbacks; one selected factor changes.
Sparse features and common-source dependencies do not establish that
demographic effects are absent or certify population/locality transport.

Research source **d50f987** publishes the maintained fitter, independent
verifier, complete-query packager/reproducer, tests and region inputs.
Immutable science **441510341**, tag
`participation-adaptive-persistence-20261111-01`, has all **12 full assets**
anonymously byte/hash verified. Its **12,593,287-byte / 24-member** complete
ZIP includes the **entire** accepted 20-member predecessor archive, all
**29,924,107 bytes** of new results, every permitted sufficient input, code,
tests, query, feature/benchmark hold and exact reproduction. Archive SHA:
`c0236d56211032c8f7fdfe6f84d0bb60ea0bafb2d0df2ab16fad3e10d4f03992`.
Separate full CSVs contain 550 predictions, 78 feature decisions, 51 benchmark
decisions and 215 outer fits. Every inner fit remains in the full JSON.
Nine focused tests, **311,478 independent checks / 13,943 unique fits**, and
two fresh warning-fatal network/external-command-blocked reproductions pass
all result/query bytes and every predecessor member.

**Keep the existing live model.** There is no automatic model/UI promotion,
new precinct/county transition estimate, observed-staying-home claim, data
activation or website build. The completed map/interface audit remains live
at website **78df729**, with all 113 models and prior complete downloads
unchanged. See [the full method](docs/TRANSITION_SIMULATION.md#demographic-and-geographic-adaptive-persistence-experiment)
and [complete downloads](docs/DATA.md). Numerical/publication records:
`data/participation-model-validation/20261111-adaptive-persistence/`.

## New Jersey: complete contextual county map bindings

The two later Essex/Hudson source records now qualify on the **same unchanged
2024 contextual county geometry** used for the previous 19 NJ observations.
All 19 original exact-record-hash identities pass their accepted oracle; the
two new county headings, state, election and full sufficient source facts
match unique existing Essex/Hudson features. No coordinates, overlaps or
coastal shapes are repaired, recomputed or replaced. The complete reference
remains **139,257 bytes**, SHA
`489eabbafe98495645d95ddb65581f5204b3bd7871b001d02d3aaa3ffa11733b`.
This is contextual county identity, not certified 2026 legal election/precinct
boundaries, individual voters, turnout rates or survey allocation.

Generic source **18b3319** updates only explicit join/view-reference metadata
for the 21 supported county observations. All 107 source records otherwise
remain unchanged, including counts, denominators, missing rates, clocks,
conflicts and full native fields. Early/returned frames are untouched.
All **51** unaffected count runtime files and **29** unaffected native files
are byte-identical. Four new Native county-mode bindings retain all other
native layers, tables, municipality references and prior county modes.

Immutable science **441296396**, tag
`participation-new-jersey-county-bindings-20261111-01`, has all **six** complete
assets anonymously byte/hash verified. Its **163,001,209-byte / 116-member**
ZIP includes **all three entire** count/native/context predecessor scientific
packets, full unchanged geometry, original 19-row hash oracle within the whole
review, complete native facts, new code/tests, every 21-county/four-mode query
and both complete runtime datasets. Fourteen tests, **402 independent checks**
and two fresh network/subprocess-blocked byte-identical reproductions pass.
Archive SHA: `9039c32cb65bc42f0c412137ca413f7d4dc224250eb404a8fa6df4004da81d91`.

The existing common publisher safely activates Native **6b57129d** first
(staged **704df678**, catalog **8468f323**), then count **2de669a7**
(staged **d744c159**, final catalog **1a440f55**). All **31 + 54** immutable
files and the actual public pointer are verified; resident/scenario entries
are unchanged. Data activation has **zero website builds**.

Actual production verifies all 107 full NJ source records, all four catalog
readers, four county modes and **16 real SVG pointer/tooltip cases** on desktop
and phone. Altered reference vintages and source qualifiers are rejected;
missing rates remain null. Screenshot inspection caught a generic footer
hardcoded to 2026 despite the actual 2024 reference. The sole caption correction
is website **121fd8c**, Pages **42971691616**, guard **42971691564**, artifact
**13834575140**: actual **996,310,342 payload / 998,891,520 tar bytes**, all
**62 exact unqueried assets** and **436 unchanged complete-download pins** pass.
Thirteen count/native/coverage tests, Astro check (zero errors/warnings, eight
existing hints), the full build, four local map cases and the existing 2026
reference caption pass. Final production rechecks all 16 cases, both vintages
and every field/saved row of all **113** original models; both final images
were inspected. No new tab/sidebar or geometry repair was introduced.
Records: `data/participation-access/20261111-nj-county-bindings-02/`.

## New Jersey: two previously held county counted-mode observations

The official index declared distinct **November 10, 2026** Essex and Hudson
periodic reports. Their complete 46-row, 12-count-column factual tables retain
all blanks and source fields. Independent PDF engines checked **598 labels and
cells**; both congressional and municipal aggregate rows, and their component
rows, agree on the selected early Votes Cast + Election Day Votes Cast +
mail Ballots Tallied components. The derived subtotals are **Essex 225,368**
(45,282 + 140,183 + 39,903) and **Hudson 213,051**
(38,978 + 155,273 + 18,800).

These are source-defined counted-mode subtotals, **not certified full-election
ballots, unique people or turnout rates**. The blank county rows remain blank.
Essex's nonselected mail-processing disagreement, **11,740 versus 1,990**, is
unrepaired. Hudson's separately reported **1,200 counted provisionals** are
retained but excluded from this consistent subtotal definition. Issued,
received and pending counts are not added or used as registration denominators.
Native clocks remain **11/10/26 3:10 PM** and **11/10/26 12:21 PM**, respectively;
neither declares a timezone or counting completion.

Generic append-only source **0f10fcb** adds only these two observations.
All **105** previous NJ records, all **50** other state shards and the current
state/provider snapshot remain unchanged: **51 unaffected runtime files** are
byte-identical. Available/official/UF-context selections now contain **21**
county observations; the distinct early/returned provider frames are unchanged.
No new rate, state sum, survey allocation or geographic approval is introduced.

Immutable science **441254758**, tag
`participation-new-jersey-county-gap-20261111-01`, has **eight** full assets
anonymously byte/hash verified. The **12,360,680-byte / 79-member** complete ZIP
includes the entire prior 126-member count packet and nine-member NJ query
packet, all new sufficient facts/recipe, compiler/contracts/code/tests, updated
runtime and complete matched county queries. Original PDF/HTML presentation
and acquisition/session headers are not redistributed. Eleven tests,
**193 independent arithmetic/incremental checks**, and two fresh
network/subprocess-blocked byte-identical reproductions pass.
Archive SHA: `3a4641e43cfd6825d87e16696b5b0cf4282035327bf8de2769bc8a9883d6b8dc`.

The existing common catalog activates count version **1b1bff95**, staged
**f0479fec** / corrected catalog **411c1e20**, with all **54** immutable files verified,
all other three datasets unchanged and **zero website builds**. Website/main
remains **38a6e71**, with protected canonical HEADs/indexes and Pages IDs
unchanged. Mixed November 5/10 county clocks are not a statewide snapshot.
The first production gate caught an omitted `immutable: true` download
qualifier; a single-field, independently verified metadata correction restored
the shared reader without republishing science or changing runtime bytes.
All four actual catalog readers, all 107 full NJ records/six mode frames and
16 real desktop/phone county-detail cases now pass. Four unchanged production
script assets are byte-verified and both screenshots inspected.
At this count-only stage, the new counts were **table/selector-only**; source
possession did not approve their two map bindings. The separate qualified
reference extension above subsequently resolves those two holds.
Records: `data/participation-access/20261111-nj-county-gap-01/`.

## Conditional demographic transition simulation

The requested simulation now has a **published conditional source-frame model**,
not identified respondent histories or validated population turnout. Research
source **ddfabf7** implements finite-budget synthetic couplings over retaining,
switching, modeled nonparticipation, prior-contest nonvote entry, Other and
unresolved choices. It uses only previously released permitted whole-state
moments and disclosed broad-group inputs. The `pre1870_pop` reference supplies
budget/seed/conservation architecture only, not historical population or ancestry
assumptions. See [the full method](docs/TRANSITION_SIMULATION.md).

All **50 source states**, **300 final couplings**, **1,443 calibration-grid
couplings**, **1,500 state seed cases** and **20,130 nonadditive demographic seed
cases** are computed. All **1,530 demographic decisions**, including **671**
disclosed groups, are retained; suppressed/unavailable groups stay null. All
**113** current-return checks remain unfitted. All **89** qualified same-office
swings reconcile exactly with the synthetic signed terms, normalized-margin
denominator term and separate unallocated current/prior frame differences.
The **2,754** historical CPS decisions retain native missingness and frame breaks;
their marginals do not supply joint-transition holdout truth.

Gross switching alone, not its partisan direction or reported election counts,
calibrates a shared persistence strength against **55** current-voter tables in
**39** states. Every same-state office table is excluded from that state's fold.
The held-out MAE is **1.39 pp**, versus **1.40 pp** for the fixed factor-16
scenario, not material evidence of better population prediction. Some governor
misses exceed four points; Wyoming is approximately eight. House-model transport
to Senate/governor remains an assumption; there are no House poll targets.
Demographic prior-party associations, source sampling uncertainty, survey
independence and population transport remain unqualified. Half/double-strength
envelopes are assumption sensitivity, not confidence intervals.

Immutable release **441189732**, tag
`participation-transition-simulation-20261111-01`, has all **seven** complete
assets anonymously byte/hash verified. Its **9,977,891-byte / 20-member** ZIP
contains both entire predecessor packets, the whole permitted demographic and
corrected comparison inputs, all code/tests and every scenario/query/result.
The separate complete result is **44,360,809 bytes**; the compact viewer is
**1,900,104 bytes**. Archive SHA:
`422d14209bc6be35919e95a5b69aee6af58e9721c095453bf343139f59f883a2`.
Twelve focused tests and **2,557,140 independent scalar checks** pass, including
relative-entropy stationarity, not just moment feasibility. Two fresh
network/external-command-blocked reproductions produce every result/viewer byte
identically under different hash seeds, with numerical warnings fatal.

The conditional scenarios are now **verified live in the existing single map**
at website **38a6e71**. Keep-party-choice, switch-party-choice and modeled
nonparticipation views have demographic/source-group selection and a sequential
share scale, separate from the unchanged signed swing views. Clicking a state
retains the selected office/group and shows the five exhaustive gross outcomes,
half/double-strength envelope and separate whole-state reconciliation. Missing
groups and D.C. remain gray/unavailable, never zero. No tab or sidebar was added.

The independent `transition-scenarios-2026` dataset is version **6d90035**,
staged **ba863590** / catalog **7c9d73a6**. Both runtime files and descriptor
are anonymously verified; all three older catalog entries are unchanged.
Data activation preserved all protected HEADs/indexes and main/run IDs:
**zero website builds**. The unchanged actual production **6ee8416** loader read all
50 states / 1,530 decisions before the separate code activation. The 1.9 MB
scientific viewer stays external; its runtime gzip is **271,073 bytes**.

Actual Pages **42954156305** / guard **42954156464** / artifact **13825843761**
pass **996,310,309 payload / 998,891,520 tar bytes**, all **62** exact unqueried
assets and **436** preserved complete-download routes. All **128** new real-public
scenario cases pass across office/group/view combinations on phone and desktop,
including checksum rejection/retry and late-response isolation. All prior
176 native, 308 count, 78 resident, 59 geography, 24 original map and 32 layout
cases pass; every field of all 113 original models is unchanged. Production
phone/desktop images were inspected. Thirteen focused frontend tests, Astro
check and the full build pass. Existing unrelated source hints and the known
legacy Methods-selector validator limitation are not claimed fixed.

The immutable scientific release anchor remains **6ee8416**; its implementation source
is the separately published research commit above. Source weights/draws are not
people; modeled nonvoters are not administrative staying home; no state model
is allocated to precincts. Eligibility/death/migration and design CIs remain null.
Science records: `data/participation-access/20261111-transition-simulation-01/`.
Final live records: `data/participation-access/20261111-transition-simulation-ui-02/`.

## Additional matched-reference resident context

The four remaining mapped participation-reference families now have **1,456**
new conditional resident profiles: **448 Idaho, 710 Virginia, 159 North Dakota
and 139 D.C.** The original full scope audits, not newly repaired geometry,
identify **179 North Dakota / five D.C.** references whose clipped or prior
repair-affected footprints remain held. All 482 ND/DC reference decisions are
retained; no demographics of a clipped area are labeled as the whole unit.
One otherwise qualified North Dakota reference has no usable population/income
proxy; those metrics stay unavailable rather than becoming zero.

All **335,948** new native block decisions and exact resident arithmetic pass
**1,242,200 independent checks**. Two fresh network/DNS-blocked new-science
reproductions preserve every point/weight/profile byte and check all 239,742
native block groups in each full ACS table. Two fresh incremental runtime
reproductions and the new full-bundle mode also pass. The seven previously
accepted spatial reductions are not repeated.

Immutable release **441153023**, tag
`participation-resident-matched-context-20261111-03`, has all **three** full
assets anonymously byte/hash verified: **275,687,426 bytes / 81 members** for
the new science, **604,211,777 bytes / 85 members** for the complete resident
bundle, and **5,816,288 bytes** for the exact runtime ZIP. The complete bundle
retains both entire new and prior scientific inputs, all sufficient originals,
full queries/code/tests and the earlier native intake demonstration; it is not
a metadata-only update. Primary SHA:
`858555e7cd9ab989f411be32523757c423691b8ab0c57769e73e314db57a885a`.

Runtime version
`55600f7238c96fc8c3c36b5a7470c70609cb3f5c6e0ce1789781059c41c3e0c4`
extends resident **23a -> 556**, staged **2ee541ca** / catalog **25808ff0**.
All **53** immutable files and catalog are verified. Every existing county
record and all 47 untouched state-shard bytes are preserved, including all
**6,847** prior local profiles. The dataset now contains **3,144 counties,
8,303 local profiles / 185 held references** across 11 reference families.
Unrelated count datasets, source/canonical HEADs/indexes and main/Pages IDs
were unchanged: **zero builds for data activation**. The unchanged actual
production **e588860** reader subsequently loaded the new dataset and retained
county/Minnesota profiles with no fixture or build.

The matched-selection/hash plumbing and readable hold explanations are
implemented in **6ee8416**. Actual-public local acceptance passes **78** resident
cases across all 51 jurisdictions, all 11 reference families, both screen
widths and explicit held-reference selections. Both images were inspected.
Actual code **6ee8416** is now **verified live**. Native Pages **42944752314** /
guard **42944752242** / artifact **13823195376** pass **996,278,378 payload /
998,860,800 tar bytes**, 61 exact unqueried production assets and 436 old
downloads. All **78 actual production resident cases**, including the four
new families and explicit holds on both screen widths, pass without fixtures.
All 176 native, 308 count, 59 geography, 24 map and 32 layout cases pass;
every field of all 113 models remains exact. Production desktop/phone images
were inspected. Records: `data/participation-access/20261111-matched-resident-03/`.
Context remains conditional 2020-proxy / 2020-2024 ACS resident composition,
not voter demographics, group turnout, election-time boundary certification,
averaged median incomes or a new sampling MOE.

## Canonical native count/reference bindings and scoped coverage

The common native reader is **verified live at e588860**. It separates count
observations from fixed reference bytes across **11 mapped layers**, **134
county/local frame bindings**, **eight municipal bindings** and **five complete
reporting-only tables**. The **14,470** canonical appearances retain every
previous source field, clock, zero, unknown, conflict, withholding and geographic
qualification. They are non-additive appearances, not people. Old embedded
counts are ignored; count-only updates can reuse reference hashes and coordinates.
The original accepted source-specific qualification code supplies the frozen
compiler oracle, not the active browser qualification chain. No new native
acquisition, topology reduction, source repair or geographic approval occurred.

Immutable release **441129848**, tag `participation-native-bindings-20261111-02`,
has its entire **115,221,556-byte / 191-member** ZIP anonymously byte/hash
verified. It includes every sufficient held input, full reference bodies,
all queries, original contract/oracle, compiler/tests and offline reproduction.
Two fresh network-blocked reproductions pass the original Python contract,
all 14,470 records and all **30** runtime files. Science SHA:
`6f92f5a81b54b40189b40dace02de481a3e05912cd8bd10cb9bcfafbff6d960d`.

Dataset version
`e90970b8c6cdcddbdbd23926b6e57f818bb49952ae32c784603dda6293143f24`,
staged **ec906850** / catalog **414734fe**, is independently public with all
31 immutable files and catalog verified. Prior datasets and protected source /
canonical HEADs/indexes, main and Pages IDs remained unchanged: **zero builds**.
The code was separately activated once. Actual Pages **42939815222** /
guard **42939815230** / artifact **13820547304** pass **996,277,012 payload /
998,860,800 tar bytes**, 61 exact unqueried assets and 436 old downloads.

All **176** production native cases pass, including every binding/table, all
11 maps, phone/desktop scope coverage and explicit fault isolation. All 306
count bindings / 51 selectors, 66 resident, 59 geography, 24 map and 32 layout
cases pass; every field of all 113 `20261110-02` model records remains exact.
The final model-only check resumed after the acceptance harness initially
selected its older expected dataset; no valid deployment or completed checks
were repeated. The full legacy site validator's unrelated Methods selector
assertion remains a confirmed pre-existing limitation, not a claimed pass.
Records: `data/participation-access/20261111-native-bindings-02/`.

The coverage disclosure stays closed by default, full-width below resident
context, never a sidebar list. It follows actual selected frame inventories;
table-only sources do not imply approved precinct geography. Unknown, withheld,
missing, awaiting-publication and rejected cases remain distinct. Historical
observations are outside this 2026 catalog, not falsely marked missing.
Historical, candidate-result and survey readers remain separate.

## Canonical 2026 state/provider and county/local count migration

The one-time migration uses the complete accepted aggregate exports, not a new
native-source parse: 49 full additional-state files, the complete base query,
all reviewed county/state rows and the current state/provider snapshot. All
**24,827 source appearances** retain their full original fields, literal clocks,
conflicts, rate decisions and reference qualifications under the shared
observation contract. **616 zeros, 111 unknown counts and six explicitly withheld
counts** remain distinct. These are non-additive source appearances, not people.

All **306** original state/view selections match every field in the actual
accepted reader. The original frozen Python contract accepts every record;
two fresh network-blocked reproductions exactly rebuild all **53** runtime files.
The original record scoped this increment separately from the native migration,
now completed above. No new native or geographic qualification is claimed.

Immutable release **441081257**, tag `participation-count-migration-20261110-01`,
has all **four** complete assets anonymously byte/hash verified. The
**8,621,160-byte / 126-member** primary ZIP includes every sufficient accepted
aggregate input, every canonical query, full-observation CSV, code/tests,
original contract and exact offline reproduction. Acquisition receipt headers
and compiled publisher application code are excluded. All earlier raw-source
science and complete releases remain unchanged.

The shared publisher activated version
`b695d9e882b601001716764ebbad7aca50e44af04b635c4f60833247e0fd2996`,
staged **c3715dfe** / catalog **b3df476d**, with all 54 immutable files and catalog
verified. Source/canonical HEADs and actual indexes, main and Pages run IDs were
identical before/after: **zero builds**. Resident dataset **23a** is unchanged.
After natural mutable-catalog propagation, the local reader passed all 306
actual-public bindings, all 51 selector inventories, desktop/phone and no
obsolete 2026 count requests, without fixtures. All 59 native drilldowns,
24 single-map cases and 66 actual-public resident cases pass locally.

Website source **c4ccdf4**, native Pages **42930954947** / guard **42930955056**
and artifact **13816392978** pass deployment, **996,279,079 payload /
998,860,800 tar bytes**, all 59 exact unqueried production assets and all 436
old downloads. The reader is **verified live**: all 306 bindings plus two
viewport cases, all 51 selector inventories, 66 resident cases, 59 native cases,
24 map cases, 32 layouts and every field of all 113 models pass in production.
Desktop/phone images were inspected. One transient public-shard fetch failed;
only unfinished browser acceptance resumed, using bounded transport-only retries
from **41887bf**, without rebuilding or substituting data. Final records:
`data/participation-access/20261110-count-catalog-01/`.
The dependent native count/reference migration and coverage are completed above;
separately qualified geographic/demographic gaps remain unfinished.

## Reported same-office swing correction

Version **20261110-02**, research source **ffc72e9**, original website source **975fbf8**
and latest one-map website source **21d3d60**,
corrects the distinction between the reported return swing and the original
conditional survey-frame contributions. The 89 qualified comparisons cover
35 complete-identity House source aggregates, 26 qualified Senate references
and 28 supplied matched governor county frames. Unqualified comparisons remain
unavailable; all 113 original model records and ranges are unchanged.
The user requires **one map with selectable views**, retaining office/state,
the shared signed scale and the full reported-total equation.

House uses the complete prior six-input House packet, exact Census Gazetteer
county identities and native current district controls. Source coverage and
competition/geography qualifications remain separate. Senate uses the full
official FEC 2020 workbook's regular-seat candidate rows; Georgia uses its
January 2021 full-term runoff, not the other seat. DFL is an explicit Minnesota
party-code alias; independent/fusion/unmapped affiliations are not inferred
as Democratic coalitions. Unresolved later specials and missing party pairs
are withheld. Governor comparisons retain the supplied matched 2022/2026 frame.

All margins use `100*(D-R)/(D+R)`. The unallocated baseline-alignment term is
reported swing minus original survey-frame change; it is not fitted to people
or assigned to switching/staying home. Current native clocks, capture snapshots,
rounds, partial reporting and absent clocks remain explicit in each comparison.

Immutable release **440892459**, tag `participation-observed-swing-20261110-02`,
has three anonymously byte/hash-verified full assets. Its **4,307,149-byte**
complete packet includes both entire predecessor analysis ZIPs, the full FEC
workbook and Census Gazetteer original, every input/selector/query, code,
tests, results and hashes. Offline reproduction rebuilds both predecessor
analyses and byte-compares every new comparison. See
[interpretation and limitations](docs/RETURN_ATTRIBUTION.md).
Original Pages **42898891761** produced a fully verified artifact **13802017519**
(996,245,789 payload / 998,830,080 tar bytes; 56 exact critical assets and 436
old downloads), but deployment attempts 1 and 2 timed out. The rejected cross-run
recovery helper was removed; the validated site tree was preserved. The next
multi-map code build was intentionally cancelled at the latest user request,
not described as a failed numerical/reader validation.

Latest source **21d3d60** adds a single view-selectable map and the default-closed,
full-width resident disclosure below the atlas. Reader checks pass all 51
jurisdictions, native county missingness, exact conditional-reference hashes,
late-response/error isolation and election-year changes. Current county catalog
**496a** is genuinely public; local **23a** browser fixtures are not publication.
Actual Pages **42916341779 attempt 1** / guard **42916341788** /
artifact **13810247294** are verified live: **996,264,664 payload /
998,850,560 tar bytes**, 58 exact unqueried assets, all 113 model records,
24 office/view/viewport cases, 55 actual-public county cases, 59
geography/native cases, 32 layouts and all 436 old complete downloads.
Production desktop/phone images were inspected. Final records supersede
the earlier pending state:
`data/participation-access/20261110-single-map-reader-01/observations.json`
and `website-acceptance.json`.

## Direct county resident context and independent data publication

The common backend source **01adfc2** reduces the complete public **2020-2024
ACS five-year** B19013, B03002, B19001, B15003 and B01001 tables into income,
exclusive race/Hispanic-origin, age and education context for **3,144 native
Census counties / 51 jurisdictions**. All 3,143 observed income medians remain
literal; the unavailable median for 35011 remains unavailable. Native MOEs,
special codes, source periods and 2024-dollar income definitions are preserved.
No voter profile, demographic turnout, averaged median or derived MOE is inferred.

Immutable release **440794066**, tag `participation-resident-counties-20261110-01`,
has **nine anonymously byte/hash-verified full assets**. The complete
**159,566,534-byte / 142-member** packet includes all five full ACS originals
(462,776,851 bytes), the complete native Gazetteer original, all 51 approved
unchanged county references, full native/runtime queries, code, tests and
checksums. **2,247,960 independent checks**, 32 packaged tests and two fresh
network/DNS-blocked reproductions pass; every native query and all 52 runtime
files reproduce exactly.

The common publisher activated content-addressed runtime version
`496a4245fae201722492a4396a36f05a04600476a662d0974480a5e59cb3fb3a`
on the separate `participation-data` ref, catalog commit **f120331a**.
All 53 immutable files and the catalog were verified anonymously. Website main,
source worktree HEAD/index and Pages run IDs were unchanged: **zero builds**.
That first county-only publication was followed by actual live reader
activation at **21d3d60** and a second same-dataset update to **23a** below.
The replacement canonical count reader and coverage interface remain unfinished. Full records:
`data/participation-access/20261110-resident-counties-01/`.

## Linked swing maps and compact navigation: verified live

Participation source **3389e1f** replaces the bar list with linked state maps for switching and
modeled nonparticipation, retains House/Senate/governor selection and full
seven-term detail, and removes only the redundant Precincts top navigation.
All 113 model records, States drilldowns, old URLs and downloads are preserved.
Desktop/mobile local map, legacy-drilldown and 32 layout checks pass.

Actual source **ecd0aca**, Pages **42884589720 attempt 1** / main guard
**42884589710** / artifact **13794714671**, passes **996,077,623 payload /
998,656,000 tar bytes**, 56 exact production files and all 436 old download
routes. All 59 geography/legacy-drilldown cases, 32 layouts, six linked-map
office/viewport cases and every field of the 113 model records pass.
Desktop and phone production screenshots were inspected.

The earlier Pages **42875076282 attempts 1 and 2** timed out despite their
bounded retries. A concurrent authorized UK publication advanced main and
picked up the unchanged participation code. That actual new artifact and
production were accepted; no competing rebuild was queued and the other
publication's workflow changes were preserved. Full records:
`data/participation-access/20261110-swing-maps-01/`.

### Conditional local resident context: accepted native-point reduction

The corrected common source **d9f1c09** applies local ACS cells to **6,847**
valid references across MN/NM and the supported portions of MI/IN/AK/NH/MA;
one invalid Michigan reference stays held. A native shared-edge regression
exposed projected-chord misclassification in the unpublished pilot. The fix
tests untouched geographic-coordinate edges and holds every boundary tie.
All 33 backend tests and both remote source checks pass.

Independent scalar membership and exact-Fraction checks pass **3,884,575**
checks across **933,012** complete block decisions and every saved profile.
No reference is repaired, no original reacquired, no source ballot count
allocated and no median income averaged. 2020 proxy placement, 2024 block-group
code equivalence and within-group composition remain explicit assumptions.
The **306,928,470-byte / 122-member** complete precinct packet and
**322,942,792-byte / 85-member** all-in-one dataset bundle are now prepared.
Two full scientific offline reproductions pass, including all 239,742 block
groups in each full ACS table. Two additional runtime-only reproductions reuse
that accepted science and exactly reproduce all 52 files; they are not extra
raw-input scientific reductions. Frozen backend **3814854** has all 35 tests
and both source checks passing. All **11** full assets are now anonymously verified in immutable release
**441018651**, tag `participation-resident-local-context-20261110-02`.
The common publisher promoted the exact ready dataset to staged **373c3de2** /
catalog **bb4dafa0** on `participation-data`, version
`23a94afd67693e09f23401ee7dfac50583d3a1aee26ca5cc929a4c2520d5f828`.
All 53 immutable files and the catalog passed anonymous checks. Website main,
the source HEAD/index and Pages run IDs remained identical: zero site builds.
After the mutable catalog cache naturally propagated, the live reader passed
all **66** direct production county/local-reference/viewport/year cases with
no test fixture. It shows direct county context and conditional local profiles
separately, requires exact loaded reference hashes, preserves the missing 35011
income and never turns resident composition into voter composition.
Both production screenshots were inspected. Other unsupported local/historical
contexts remain explicitly unavailable. Full final records are linked above.

## 2026 modeled NORC and returns bridge

The new experimental bridge reuses the already-reduced whole-state NORC
moments, held House district controls, 35 native Senate vectors, all 2,014
supplied governor factual county records and 55 qualified office-specific
main switching tables. It computes **113 conditional estimates / 1,017
strength scenarios** without rerunning the successful original survey reduction.
Private fine joint/demographic cells and respondent records are not selected.

Five tests, **10,565 independent Fraction checks** and two exact network-blocked
reproductions pass. A complete **749,940-byte / 14-member** packet contains all
sufficient selected numerical inputs, full queries, code, tests and checksums.
All six full assets are anonymously checksum-verified in immutable release
**440640408** before website activation. Website **b3929d2**, Pages
**42859217257 attempt 1** / artifact **13784767830**, passes
**996,055,796 payload / 998,635,520 tar bytes**, exact production assets,
all 113 embedded records, all three office interactions and 32 layout cases.
All **436** earlier complete-download routes are unchanged. The
[methods note](docs/RETURN_ATTRIBUTION.md) distinguishes source-frame contrasts,
transport, the exact denominator term and the unallocated return/frame gap.
The baseline is recalled 2024 President, not automatically a prior election
for the same office; modeled nonparticipation is not measured staying home.

## Clear swing comparisons and local maps

Website **b30339e** makes **2026 swings** a primary tab, with state links
and separate House, Senate and governor controls. The original 113 model
records are unchanged. Supporting studies now have three default-closed,
purpose-labeled groups rather than an undifferentiated component list.

The selected border follows the exact displayed county footprint, not a
coarser state outline. All **49 county-result states** and six mobile cases
pass. Precinct views add source-unit search, county/locality filtering,
loaded-footprint fit and actual count/rate totals. A real Minnesota zero,
unsupported 2026 selections and North Carolina's 2024 history are checked.
No counts, clocks, original shapes or qualifications are repaired.

Actual Pages **42867075038 attempt 1** / artifact **13787703374** passes
**996,064,265 payload / 998,645,760 tar bytes**, exact production assets,
59 border/precinct cases, 40 width/tab layouts, six office interactions and
exact equality of all 113 embedded records. All **436** old complete-download
routes remain available. Full machine records are under
`data/participation-access/20261110-clear-views-01/`.

### Earlier all-state sidebar fix

Website `e7ddf5f` removes unfiltered county-button lists generically, not just
for Florida. Actual Pages **42850112990 attempt 2** / artifact **13781711302**
passes **995,790,625 payload / 998,369,280 tar bytes**, 54 exact unqueried
production files and 436 unchanged full-download routes. All **102 live
state/viewport cases** pass, including all 50 loaded local-count selectors;
actual map clicks, compact selection, selected details and 32 shared-margin
checks remain intact. The failed deployment was recovered with the same
original artifact, not another build or upload.

## 2026 Minnesota complete native statistics

Source `592c7df` uses the genuinely new **November 10, 8:08 AM** native
statistics snapshot; timezone unknown. The
[complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-minnesota-complete-native-statistics-20261110-03/complete-analysis.zip)
is **71,548,414 bytes / 57 members**. All eight sufficient inputs include
the **entire earlier 50,849,478-byte / 80-member original package**, every
new native row, full page numerical fields and complete comparisons, plus
all maintained code/tests/queries and exact offline reproduction.
Immutable **440502731** / all 13 full assets and the browser-safe, tag-pinned
9,223,418-byte native reference were anonymously verified before main.

| Scope | Treatment |
|---|---|
| Complete source reporting | All 87 counties / 4,105 native rows explicitly report. Fillmore, Hubbard and Wright close the 26 earlier unknowns. Keep 32 reported zeros as zeros, not missing. |
| Counts and registers | Derived native Total Number Voted sum 2,852,618 equals the separately labelled Estimated Voters display, but that estimate never supplies missing counts. Keep 7AM registrations 3,927,697 and Election Day registrations 147,357 separate. |
| Qualified fractions | Existing source-register rules qualify 73 county fractions; 14 remain withheld. Preserve all 60 component conflicts and six precinct electorate excesses. Every precinct analysis rate stays null; no unique-person, certification or demographic claim. |
| References and history | Every one of 4,105 coordinate hashes matches the prior full September 18, 2026 reference. Reuse all 13,619 pair reviews without another geometry acquisition/intersection campaign. Keep every earlier reader, reference and full route; native properties are not geometry repairs or certified legal precincts. |

All 208 affected Node checks, three Python checks, four staging-safety checks,
Astro/build and actual desktop/mobile full-count/zero/new-unit selections,
Methods/modes/rejection/retry, all204 controls, all51 geography and preserved
Nevada17 pass. Independent verification passes **91,191 checks and two
exact blocked-network reproductions**, each with three Python and two Node tests.
Actual Pages **42839445026 attempt 1** / main guard **42839445105** passed:
artifact **13774599591**, **995,766,815 payload / 998,348,800 tar bytes**.
All **52 exact unqueried production paths**, 436 unchanged full-download
routes and eleven production suites pass, including all 26 newly reported
unit selections, all204 mode controls and all51 geography. The bounded
deployment retry reused the same artifact; no rebuild or reupload.
The complete Minnesota view is now verified live. The
[source record](data/participation-access/20261110-minnesota-complete-native-03/observations.json)
and [website status](data/participation-access/20261110-minnesota-complete-native-03/website-acceptance.json)
retain the actual proofs. Broader coverage and the common-intake replacement
remain open.

## 2026 Nevada distinct county participation snapshots

Source `3e20b0d` adds three distinct official reports and reuses Washoe unchanged.
The [complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-nevada-native-counties-20261110-01/complete-analysis.zip)
contains all **18 sufficient inputs / 53 members / 1,539,042 bytes**: two full
PDFs / 23 pages, all 147 Clark numerical tables and factual text, every held
Washoe sufficient file including its full 23-page numerical text, all 17
unchanged county references, all 136 pair decisions, queries, code and tests.
Immutable **440439566** / all 12 full assets were anonymously verified before main.

| County | Native participation count | Literal source clock; timezone unknown |
|---|---:|---|
| Clark | 745,317 Total Turnout | Page updated 11/09/26 06:46 PM |
| Churchill | 9,685 Voters Cast | PDF generated 11/5/2026 10:56:17 AM |
| White Pine | 3,077 Voters Cast | PDF generated 11/3/2026 7:48:47 PM |
| Washoe, held unchanged | 191,830 Voters Cast | PDF generated 11/4/2026 6:13:35 PM |

These are **four separate unofficial snapshots, not a statewide total**.
Thirteen county counts and registrations remain unknown, not zero or candidate
votes. Native registers and printed percentages survive; all analysis rates
stay null. Churchill's separate House District 4 Times Cast 1 / register 0 /
N/A remains literal, never a county denominator. Counting groups are not
precincts; existing provider early/returned frames remain separate and unchanged.
The 2026 Census county context is not certified election precinct geography.
State SilverState/VIVID security-challenge routes remain stopped, without
another client, cache, mirror or key.

All 205 affected Node checks, six Python checks, Astro/build and real
desktop/mobile Nevada clicks, 13 unknowns, Methods/modes, rejection/retry,
all204 mode controls, all51 navigation and preserved AL67 pass locally.
Independent verification passes **351 checks and two exact network-blocked
reproductions**, each with six Python and two Node tests. Actual native
Pages **42830450810 attempt 2** / main guard **42830450991** passed:
artifact **13771252796**, **995,761,527 payload / 998,338,560 tar bytes**.
All 51 exact unqueried production files and eleven suites pass: Nevada17
desktop/mobile, all204 controls, AL67, MN84/4105, MA307, NH37, IL102, AK81,
ME480, HI4 and all51 geography. No valid source request was overridden.
The first attempt's deployment and built-in retry timed out during file
sync; failed-job-only recovery reused the same artifact and passed, with
no rebuild, reupload or new artifact. All 436 old full routes are unchanged.
The [source record](data/participation-access/20261110-nevada-native-counties-01/observations.json)
and [website status](data/participation-access/20261110-nevada-native-counties-01/website-acceptance.json)
retain the actual proofs. Broader county/precinct and population gaps remain open.

## 2026 local source-mode frame review

Source `fbbaef9` prevents unsupported local early/returned selections from
reusing unrelated observations. The
[complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-native-mode-frames-20261110-01/complete-analysis.zip)
contains all **58 sufficient inputs**, 49 complete local exports, shared native
inputs, all 464 reviewed county observations, original selectors and all
**204 before/after decisions** with full selected-observation queries, code,
tests and exact reproduction; **4,001,794 bytes / 86 members**.
Immutable **440383617** / all eight full assets were anonymously verified
before main activation.

| Scope | Treatment |
|---|---|
| Corrected selection | 23 unsupported choices across 16 jurisdictions no longer expose all-method ballots, town VV, TOTAL TURNOUT, Cards Cast or other unqualified frames. Missing mode qualification is explained, not treated as zero or missing ingestion. |
| Preserved evidence | All 102 Available/official decisions and 67 qualified requested-mode decisions remain unchanged. Every native input count, registration, clock and printed percentage is retained; no normalized mode, population or demographic participation is inferred. |
| Full merged context | Reviewed D.C./PA/SD rows add four cases beyond the preliminary 19-case audit. D.C.'s existing 185,086 Available/official count stays; no separate export is not proof of source absence. Native precinct paths remain separately mode-gated. |

All 225 affected Node checks, Astro/build and actual desktop/mobile **all204**
control outcomes pass, including Methods/state/mode retention, all51 geography
and preserved AL67 count/negative/retry tests. Independent Python verification
passes **1,242 checks and two exact network-blocked reproductions**, each with
three Node tests. Complete CSV query fields are retained without truncation.
The [source record](data/participation-access/20261110-native-mode-frames-01/observations.json)
and [website status](data/participation-access/20261110-native-mode-frames-01/website-acceptance.json)
separate those proofs from deployment. **Actual native production acceptance
passed:** Pages **42822734036 attempt 1** / main guard **42822734054**, artifact
**13767698882**, **995,749,311 payload / 998,328,320 tar bytes**. All 50 exact
unqueried production paths and ten browser suites pass: all204 controls on
desktop/mobile, AL67, MN84/4105, MA307, NH37, Illinois102, Alaska81, Maine480,
Hawaii4 and all51 geography. Valid source requests were not overridden.
Deployment succeeded first try; the bounded same-artifact retry was skipped.
Every earlier release and all 436 old full-download routes are preserved.
This review does not close nationwide county/precinct or population-validation gaps.

## 2026 Alabama native county Ballots Cast

Source `2a33e0e` connects all **67 already-held native county counts** to
explicit, full 2026 Census county references. The
[complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-alabama-native-county-counts-20261110-02/complete-analysis.zip)
contains all 11 sufficient inputs, the full original workbook, selected
county/state factual fields, all 67 county and 2,211 pair queries, code, tests
and exact offline reproduction; **2,475,620 bytes / 43 members**.
Immutable **440343462** / all nine full assets and the runtime county reference
were anonymously hash-verified before main activation.

| Scope | Treatment |
|---|---|
| Native counts | Ballots Cast 1,693,621 and separate registrations 3,852,947 reconcile across all 67 counties. Original percentages and county clocks stay literal; timezone is unknown. All analysis rates remain withheld. |
| Identity | Source codes are election ordinals, not FIPS: 01 Jefferson joins 01073, not 01001. Preserve both source/reference names, old county IDs and counts. All 67 reference shapes are valid and all 2,211 pairs have zero positive overlap, without repairs. |
| Limits and modes | Source reporting is not certification or independently deduplicated people. No new precinct or demographic participation claim. All-method counts never fill unsupported early/returned frames. Frozen legacy reads remain unchanged. |

All 222 affected Node checks, eight Python checks, Astro/build and real
desktop/mobile all-67-value/selector tests pass, including native fields,
Methods/modes, genuine map clicks and rejected-count recovery. All51 and
preserved MN84/4105 navigation pass using the real published reference.
Independent verification passes **65,062 checks and two exact network-blocked
reproductions**, each with four Python and two standalone Node tests.
The [source record](data/participation-access/20261110-alabama-native-county-counts-02/observations.json)
and [website status](data/participation-access/20261110-alabama-native-county-counts-02/website-acceptance.json)
separate those proofs from deployment. **Actual native production acceptance
passed:** Pages **42817335682 attempt 1** / main guard **42817335689**, artifact
**13765632795**, **995,748,414 payload / 998,328,320 tar bytes**. All 50 exact
unqueried production paths and nine browser suites pass: AL67 desktop/mobile,
MN84/4105, MA307, NH37, Illinois102, Alaska81, Maine480, Hawaii4 and all51
navigation. Valid source requests were not overridden. Deployment succeeded
first try; the bounded same-artifact retry was skipped. All earlier releases
and 436 full-download routes are preserved. Nationwide county/precinct
completeness remains open.

## 2026 Minnesota native county and precinct follow-up

Source `7ff1c82` connects the already-held native follow-up: **84 complete
counties and all 4,105 full-native reference joins**. The
[complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-minnesota-native-county-followup-20261110-02/complete-analysis.zip)
contains all 34 sufficient inputs, full current/previous statistics and three
full native geometry pages, queries, code, tests and offline reproduction;
50,849,478 bytes / 80 members. Immutable **440301764** / all 17 full assets and
the external native map were anonymously hash-verified before main activation.

| Scope | Treatment |
|---|---|
| Counts | 4,079 reported Total Number Voted rows; 26 unknowns in Fillmore, Hubbard and Wright remain unknown. The 2,827,091 subtotal is not an exact statewide count or the separate Estimated Voters 2,852,528. |
| Denominators | 71 qualified county fractions use native 7AM plus Election Day registrations. Preserve 60 component conflicts and seven precinct electorate excesses; no precinct analysis rates. The November 2 registered-only snapshot stays separate. |
| Identity and references | Native countycode/pctcode and separate VTD/FIPS control all 4,105 joins; county IDs are not FIPS. Preserve both names in 1,723 differing-name joins. Full native September 18, 2026 references are not certified election-day legal boundaries. |
| Geometry and clocks | All full native shapes are valid; all 13,619 bbox-candidate pairs have zero positive overlap. Older 16 invalid generalizations remain unrepaired and unused. Native results-page update 11/07/26 5:18 PM has unknown timezone; file receipts are not update clocks. |

All 219 affected Node checks, four Python tests, Astro/build and local real
desktop/mobile county/precinct navigation pass. Independent verification passes
82,069 checks and two exact network-blocked count/reference reproductions.
The [source record](data/participation-access/20261110-minnesota-followup-02/observations.json)
and [website status](data/participation-access/20261110-minnesota-followup-02/website-acceptance.json)
separate those proofs from deployment. **Actual native production acceptance
passed:** Pages **42811573387 attempt 1** / main guard **42811573411**, artifact
**13762990964**, **995,727,090 payload / 998,307,840 tar bytes**. All 49 exact
unqueried production paths and eight browser suites pass: MN84 desktop/mobile,
MA307, NH37, Illinois102, Alaska81, Maine480, Hawaii4 and all51 navigation.
The map uses the actual immutable external reference, not a local override.
Deployment succeeded first try; the bounded same-artifact retry was skipped.
Every earlier release and all 436 old complete-download routes are preserved.
Nationwide precinct completeness remains open.

## 2026 native ward counts in four New Hampshire cities

Source `128c867` adds six direct Dover references while preserving all 31
earlier features, 242 source fields and 37 native ward rows. **Full source,
offline reproduction and live website acceptance verified.**
The [complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-new-hampshire-native-ward-reference-20261110-04/complete-analysis.zip)
contains all 160 sufficient inputs, 17 full PDFs / 219 pages, full numerical
queries, code, tests and five-generation offline reproduction; 98,854,240 bytes /
233 members. Earlier complete releases and public routes remain unchanged.

| Scope | Treatment |
|---|---|
| Counts | Manchester12, Concord10, Nashua9 and Dover6; Dover's six literal totals sum to printed15,941. Source registers, percentages, disagreements and separate federal-only fields remain literal, not analysis rates. |
| References | State-published2022 NHGRANIT layer11, not oldlayer5, private app keys or parcels. Literal Dover district labels, not FID-as-ward or nativeFIPS17010-as-county, control joins. |
| Precision and limits | Native3437/declared inverseESRI108190 preserves all1,987 vertices/cyclic edges at strict1e-9degree tolerance;15 native Dover pairs have zero overlap. All earlier shapes/overlaps remain unrepaired. Four cities, not whole-state/county totals or certified2026 legal precincts. |

All 213 affected tests, Astro/build, actual NH desktop/mobile six-ward clicks,
Methods/navigation/zoom/source guards/retry, preserved MA307 and all51 navigation
pass locally. Independent verification passes 3,031 checks and two exact
network-blocked reproductions of five generations, with16 Python/16 Node tests
each. Source release and actual native Pages/production acceptance are recorded
separately in the [source record](data/participation-access/20261110-new-hampshire-ward-reference-04/observations.json)
and [website status](data/participation-access/20261110-new-hampshire-ward-reference-04/website-acceptance.json).
Immutable **440231597** / all14 full assets were anonymously verified before
main. Pages **42801350131 attempt1** / main guard **42801349742** succeeded;
artifact **13756916795** passes **995,709,635 payload /998,287,360 tar bytes**.
All47 exact unqueried production files and NH37 desktop/mobile, preservedMA307,
Illinois102, Alaska81, Maine480, Hawaii4 andall51 browser suites pass. Deployment
succeeded on its first step; the bounded same-artifact retry was correctly
skipped, not exercised. All436 earlier full-download routes are unchanged.
Nationwide precinct completeness remains open.

## 2026 Massachusetts direct city precinct references

Source `f0156f8` closes four geographic joins with actual city polygons, not
clipped parent remainders. **Full source/download and live website acceptance
verified.** The
[complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-massachusetts-city-precinct-reference-20261110-02/complete-analysis.zip)
contains **84 sufficient inputs, four full PDFs / 648 pages**, the full
eight-member city ZIP, all 99,980 pair decisions, queries, code and exact
reproduction; 22,398,610 bytes / 146 members.

| Scope | Treatment |
|---|---|
| Joins | Boston 275 stays unchanged; all 32 Somerville units use original city polygons. Duplicate native IDs stay distinct by literal Ward/Precinct. |
| Source meaning | Counts, zero registers, differing Boston fields and Official/UnOfficial labels remain literal. Two city snapshots, not statewide/county totals, unique people or analysis rates. |
| Precision | All 2,697 new vertices and cyclic edges pass strict 1e-9-degree checking; retain exact survey-feet WKT/inverse ESRI108190, not rounded EPSG2249 or arbitrary vertex sorting. |
| Clocks and limits | City metadata September 22, 2023 / 2020 Census basis is not a certified 2026 boundary vintage. Municipal 350/351 context, invalid Wayland and Boston's two overlaps remain unchanged. |

All 211 affected checks, Astro/build and real MA desktop/mobile four-join clicks,
Methods/navigation/zoom/source guards/retry, all51 and preserved NH31 pass locally.
Independent verification passes 3,194 checks with a different binary reader
and two exact network-blocked reproductions: 11 reader outputs, two normalized
queries, 11 CSVs and eight packaged tests each. All earlier releases and 436
complete-download routes remain intact; no acquisition or source repair was repeated.

Immutable **440187428** targets `f0156f8`; all 16 full assets were anonymously
verified before main. Pages **42794958168 attempt 2** / main guard
**42794958425** succeeded. Actual artifact **13751979967** passes both caps:
**995,458,357 payload / 998,031,360 tar bytes**. All 45 exact unqueried production
files and MA307 desktop/mobile, NH31, Illinois102, Alaska81, Maine480, Hawaii4
and all51 browser suites pass. The first file-sync timeout remains recorded;
failed-job-only recovery reused the same verified artifact without rebuilding
or redownloading it. The [source record](data/participation-access/20261110-massachusetts-city-precinct-reference-02/observations.json)
and [website status](data/participation-access/20261110-massachusetts-city-precinct-reference-02/website-acceptance.json)
keep that distinction explicit. Nationwide precinct completeness is not claimed.

## 2026 Massachusetts native reporting counts

Source `5432c4a` connects Boston and Somerville while preserving every earlier
source and complete download. **Complete analysis and live website acceptance
verified.** The
[complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-massachusetts-native-local-counts-20261110-01/complete-analysis.zip)
contains **four full PDFs / 648 pages**, 67 sufficient inputs, all count/reference
queries, code, tests and exact offline reproduction; 21,432,354 bytes / 100 members.

| Scope | Treatment |
|---|---|
| Boston | Native Times Cast 185,569 agrees across six complete statewide contexts and their web fields. Separate summary Voters Cast 556,369 / registered 0 / N/A stays literal. All 44 contexts and 5,775 rows remain distinct. |
| Somerville | Printed ballots 64,597 and registrations 56,008 reconcile to 32 reporting rows; counts above registers and Official-page/UnOfficial-PDF labels are retained, not repaired or treated as unique people. |
| Reporting references | Boston 275 / Somerville 28 mapped references; four split-parent count joins stay table-only, with no clipping or invented remainders. All 307 source rows remain. |
| Municipal context | All 351 original decisions retained; 350 valid shapes display. Invalid Wayland and native Boston overlaps are not repaired. Not whole-state/county turnout or certified 2026 legal precincts. |

Per-product declared datum operations preserve the strict coordinate tolerance.
No candidate sums, Central Tabulation addition, population/geographic allocation
or analysis rates. Private page/app code, keys, contacts and unrelated feature
data are excluded. All 436 earlier complete-download routes remain unchanged.

All 205 focused tests, Astro/build, actual desktop/mobile maps and navigation,
Methods/selection/zoom/resize/source guards/retry, all51 navigation and preserved
NH31 checks pass locally. Independent verification passes 2,720 archive checks
and two exact network-blocked reproductions, with four packaged tests each.
Immutable **440115869** targets `5432c4a`; all 14 full assets were verified
anonymously before main. Pages **42784448706 attempt 2** / main guard
**42784448671** succeeded. Actual artifact **13748107256** passes both caps:
**995,165,787 payload / 997,734,400 tar bytes**. All 43 exact unqueried production
files and MA desktop/mobile, NH31, Illinois102, Alaska81, Maine480, Hawaii4
and all51 browser suites pass. Attempt 1 timed out at file sync; the
failed-job-only recovery reused the same verified artifact, without rebuilding
or redownloading it.
The [source record](data/participation-access/20261110-massachusetts-native-local-counts-01/observations.json)
and [website status](data/participation-access/20261110-massachusetts-native-local-counts-01/website-acceptance.json)
separate source publication from live acceptance. Nationwide completeness is not claimed.

## 2026 native ward counts in three New Hampshire cities

Source `a7cd4a5` adds nine Nashua ward references to Manchester's 12 and
Concord's 10. **Complete download and live website acceptance verified.**
The [complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-new-hampshire-native-ward-reference-20261110-03/complete-analysis.zip)
contains **17 full PDFs / 219 pages**, 140 sufficient inputs, code, tests,
results, all 31 reference decisions, 36 Nashua pair decisions and six Dover holds.

| Scope | Treatment |
|---|---|
| Counts | Nashua's nine printed ward totals sum to 33,849, not a separately printed city total. The component sum of 33,847 is not substituted. |
| Source disagreements | Ward 3/4/8 differences of +1/-2/-1 and printed amendments remain; federal-only 92 stays separate, never added. |
| Reference | City-linked adopted Ward polygon layer 7, effective December 28, 2021; not proposed wards, polling points, blocks or parcels. The current map's October 2026 revision is a separate clock. |
| Geometry | All 8,256 new vertices verified; nine valid, untouched shapes and all 36 pair decisions, with no native overlaps. |
| Limits | Six Dover wards remain table-only. Municipal display references are not certified 2026 legal precincts; no geographic allocation, analysis rates or unique-person claims. |

The **97,907,540-byte / 184-member** ZIP has SHA-256
`5802a9a7f17a67bd045b39447db30e44b359ab4ce2c8cc4ca782fe38524c3963`.
All 242 earlier source fields, 37 ward rows, 22 features and 436 complete-download
routes remain exact. Verification passes 202 focused checks, build and local
desktop/mobile navigation, plus 1,067 independent checks and two exact
network-blocked reproductions. Private app code, keys and unrelated feature
data are excluded. The independently declared adopted source does not replace
the recorded failure of the original NewGIS backend.

Release **440041905** targets `a7cd4a5`; all 13 full assets were anonymously
verified before main. Pages **42773036449 attempt 1** and main guard
**42773036375** succeeded. Actual artifact **13742538594** passes both caps:
**989,504,509 payload / 992,071,680 tar bytes**. All 38 exact unqueried production
files and live NH31 desktop/mobile, Illinois102, Alaska81, Maine480, Hawaii4
and all51 browser checks pass. No national precinct-completeness claim is made.
The [source record](data/participation-access/20261110-new-hampshire-ward-reference-03/observations.json)
and [website status](data/participation-access/20261110-new-hampshire-ward-reference-03/website-acceptance.json)
retain that distinction. The earlier accepted 22-ward version and every full
immutable release remain unchanged.

## 2026 native ward counts in Manchester and Concord

Source `d7e6664` preserves all earlier source values and adds ten Concord ward
joins alongside Manchester's twelve. **Full numerical release and actual
22-ward live website acceptance are verified.**
The [complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-new-hampshire-native-ward-reference-20261110-02/complete-analysis.zip)
contains **17 full PDFs / 219 pages**, all124 sufficient inputs, original
geometry, code/tests/results, all22 reference decisions and every15 held ward.

| Scope | Treatment |
|---|---|
| Concord | Ten native `Total Cast` ward values sum to printed city parent 19,234; school-district components and printed ward subtotals stay unchanged |
| Current reference | City-declared Voting Wards REST53; city approval November8,2021, while `PubWebGIS2020` is a service name, not a boundary vintage |
| Coordinate check | All4,147 new vertices use native EPSG3437 and declared **inverse Esri108190**; the wrong default null-offset operation is rejected, not hidden by relaxed tolerance |
| Topology | All shapes valid without repair; all45 Concord pair decisions and14 native overlaps retained in **projected US survey ft²**, not metres or geodesic areas; six earlier Manchester overlap records stay separate |
| Nashua / Dover | Nine / six wards remain table-only: Nashua query backend unavailable; Dover's named map is opaque and its independent public-portal ward search has zero items |
| Boundaries and rates | Current municipal display context, not certified2026 legal precincts; no source repair, allocation, analysis denominator/rate or unique-person claim |

The **97,239,222-byte / 160-member** ZIP has SHA-256
`f056052267e926feae4576aeba6be9f6caa7364a6b2d9ff4939acdf1d944d378`.
All earlier242 source fields,37 ward rows and12 Manchester features are exact.
Independent verification passes **934 checks / two exact network-blocked
three-generation reproductions**, with20 packaged tests each. All200 focused
checks, Astro/full build, actual desktop/mobile four-city/22-ward navigation,
both-city selection, zoom/resize, Methods, source guards/retry and all51 pass
locally. All436 old complete-download routes are unchanged. Nashua's complete
current map prints effective/revised **October2026**; neither its2022 service
name nor a stale cached page snippet supplies a geometry date.

Immutable **440018547** targets `d7e6664`; all12 full assets were anonymously
verified before main. Source guard **42769025074** passes. Fresh Pages
**42769170439 attempt1** / main guard **42769170432** succeeded. Actual native
artifact **13740844615** passes **989,278,818 payload / 991,846,400 tar bytes**
and all36 selected-file checks. All36 exact unqueried production files,
NH four-city/22-ward desktop/mobile counts, both-city tab selection,
zoom/resize/Methods/source guards/retry and Illinois102 / Alaska81 /
Maine480 / Hawaii4 / all51 production browsers pass. All436 old complete
routes remain unchanged; neither full-state ward coverage nor certified2026
legal precincts are claimed.
The [source record](data/participation-access/20261110-new-hampshire-ward-reference-02/observations.json)
and [website status](data/participation-access/20261110-new-hampshire-ward-reference-02/website-acceptance.json)
separate those stages. The accepted 12-ward publication below and all earlier
full packages remain available.

## 2026 Manchester native ward counts on current municipal context

Source `5fd7549` preserves the four New Hampshire city sources and adds
Manchester's **12 literal ward totals** on current official municipal ward
context. **Full numerical release and actual live website acceptance verified.**
The [complete ZIP](https://github.com/hanshanley/margin_of_error/releases/download/voter-manchester-native-ward-reference-20261110-01/complete-analysis.zip)
contains **16 full PDFs / 218 pages**, all 93 sufficient input pins, original
projected/geographic geometry, code, tests and every mapped/held decision.

| Question | Treatment |
|---|---|
| What is mapped? | Twelve native November 3, 2026 Manchester ward totals; derived sum 38,562, not a separately printed city parent |
| Which boundaries? | Current official `Wards_2022` municipal reference; clerk/map corroborate lines effective December 21, 2021, not newly certified 2026 legal precincts |
| How are identities matched? | Literal city and ward number/label; REST polygon layer **3**, not WMS layer 0 or REST layer 0's unrelated points |
| What remains unaltered? | Ward 7 prints 2,712 against components 2,797; the 85-ballot disagreement and separate federal-only 76 remain; six small native boundary overlaps are not clipped/repaired |
| What is not mapped? | Other 25 ward source rows remain in tables; default state navigation retains four-city municipality context, not a Manchester-only statewide substitute |
| What is not estimated? | No analysis denominator/rate, unique-voter count, geographic allocation or legal-boundary certification |

The **94,979,235-byte / 122-member** ZIP has SHA-256
`d2c4f2c666eeb2e696c7997d3d0d7910deaf553baa0512e2bed7cdbb670e9194`.
All earlier **242 source fields and 37 ward rows** reproduce exactly.
Independent verification passes **4,506 checks**, checks all **3,789 native
vertices**, and reproduces both new and prior city queries exactly in two
network-blocked extractions, with 14 packaged tests each. All 198 affected
tests pass; the viewport fix additionally passes 143 UI tests, Astro and full
build. Actual desktop/mobile counts, unknown areas, zoom/pan/resize, tab
selection, Methods, checksum rejection/retry and wrong-layer rejection pass;
the final all51 navigation audit passes. Private app configuration, compiled
publisher code and personal/population attributes are excluded.

Immutable release **439988155** targets `5fd7549`; all **11 complete assets**
were anonymously verified before main activation. Source guard `42763474498`
passes. Fresh Pages **42763626040 attempt 1** and main guard **42763626097**
succeeded. Actual native artifact **13738453245** passes **989,164,442 payload /
991,733,760 tar bytes** and all34 selected-file checks. All34 exact unqueried
production files, NH four-city/12-ward desktop/mobile counts, source conflicts,
zoom/resize/tab selection, Methods, source guards/retry, and Illinois102 /
Alaska81 / Maine480 / Hawaii4 / all51 production browsers pass. All436 old
complete-download routes remain unchanged. This distinct combined publication
also satisfies the earlier four-city website outcome; the old failed run is
not relabeled successful or retried. National precinct completeness is not claimed.
The [source record](data/participation-access/20261110-manchester-ward-reference-01/observations.json)
and [website status](data/participation-access/20261110-manchester-ward-reference-01/website-acceptance.json)
retain that distinction and the earlier blocked deployment history.

## 2026 New Hampshire: four city sources, not state/county or precinct turnout

Source `9b922c4` adds Nashua and Dover while preserving every original value
from Manchester/Concord. **Complete source release published; four-city
four-city-only deployment failed after three syncing-file timeouts.**
That historical failure remains below; the distinct combined `5fd7549`
publication above now provides the live four-city view and Manchester ward map.
The [complete package](https://github.com/hanshanley/margin_of_error/releases/download/voter-new-hampshire-native-cities-20261110-02/complete-analysis.zip)
contains all 15 full PDFs / 217 pages, exact native readings/crops, safe
receipts, full unchanged municipality reference, code, tests and every query.

| Scope | Treatment |
|---|---|
| Manchester | 38,562 is a derived sum of 12 printed ward `Total Ballots Cast` fields, not a separately printed city parent |
| Source disagreement | Ward 7 prints 2,712 versus 2,694 Election Day + 103 absentee; the 85 difference is retained, never corrected |
| Federal-only | Separate native sum 76, never added; inclusion in native totals independently unqualified |
| Concord | Native `Total Cast` 19,234; CSD/MVSD cells, printed ward subtotals and city parent stay distinct |
| Registration and printed rates | Opening 25,879 + Election Day registrations 1,461 = closing 27,340; source 74.32% uses opening-stock arithmetic, not an approved analysis rate |
| Nashua | Derived sum of nine printed ward totals 33,849; component sum 33,847, with Ward3/4/8 disagreements +1/-2/-1 retained; source red amendments remain literal and separate federal-only 92 is never added |
| Dover | Printed `Total Ballots Cast` 15,941; checklist 20,972 + Election Day registrations 1,484 = source registrations 22,456; native 71.0% uses that explicit basis |
| Dover definitions | Native report identifies November3,2026 despite its2025 filename; checklist verified October26; registration affiliation is not ballot choice or group turnout |
| Geography | Four cities on full 259-area **2024 municipality context**; 255 unknown areas are not zero, all 37 ward rows remain table-only |
| Qualifications | All analysis denominators/rates null; no county allocation, repaired counts, unique-voter claims or certified 2026 ward/precinct boundaries |

The **93,099,445-byte / 91-member** ZIP has SHA-256
`8722a0ba5a6f18614d08544159344aeb13672821f887ebf69865dafa85e3a2ab`.
All **242 source fields, 259 reference decisions, 28 accounting and 18
source-percent-basis diagnostics** are available. The original 107 fields,
13 PDFs and all earlier native city/ward values are unchanged. Independent
verification checks the 135 added fields, regenerates all 18 new header/count
crops pixel-exactly and passes **1,006 checks / two exact network-blocked
reproductions**, with eight packaged tests each. All **192 affected tests,
Astro and full build** pass. Desktop/mobile four-city counts/all37 ward rows,
255 unknowns, source amendments, source-register definitions, unsupported modes,
Methods and false-reference/selector-map retry pass locally; all51 navigation
passes. All four selected contextual shapes are valid without repair and
interior-disjoint. Private discovery HTML/session state is excluded.

Immutable release **439947616** targets `9b922c4`; all **ten full assets** were
anonymously verified before main activation. Main guard `42756293648` passes.
Actual artifact **13735453505** passes **989,109,680 payload / 991,672,320 tar
bytes**, all 32 selected-file checks and all 436 old complete-download mappings.
Pages `42756293558` timed out in **three deployment-only attempts**; the successful
build, same artifact and native ZIP were retained. No further retry loop or
successful build/package repetition is running. At that failure, exact unqueried
production probes still matched `452e4c9`'s two-city script/data. The later
combined `5fd7549` publication above is now separately accepted live.
The [source ledger](data/participation-access/20261110-new-hampshire-cities-02/observations.json)
and [blocked publication record](data/participation-access/20261110-new-hampshire-cities-02/website-acceptance.json)
distinguish published numerical results/local acceptance from absent live acceptance.
The earlier [complete two-city version](https://github.com/hanshanley/margin_of_error/releases/download/voter-new-hampshire-native-cities-20261110-01/complete-analysis.zip)
and [accepted production evidence](data/participation-access/20261110-new-hampshire-cities-01/website-acceptance.json)
remain unchanged. Neither statewide nor native precinct completion is claimed.

## 2026 Illinois source-region activity, not whole-county totals

The [complete immutable query package](https://github.com/hanshanley/margin_of_error/releases/download/voter-illinois-county-context-20261110-01/complete-analysis.zip)
retains both held civicAPI responses and every source-region decision. This
provider is not the Civic/NORC survey.

| Scope | Treatment |
|---|---|
| Literal records | 108 source regions per separate mode: 102 county-named and six city-named |
| Map meaning | County shapes locate the 102 source labels; they are not qualified electoral-authority territories or whole-county totals |
| City records | Bloomington, Chicago, Danville, East St Louis, Galesburg and Rockford remain separate, visible and unallocated; no single-county assumption |
| Native sums | Early 1,162,828 = 915,498 county-named + 247,330 city; returned 892,086 = 759,410 + 132,676; modes never added |
| Definitions | Literal native category `votes`, including Unspecified; not candidate choice, certified cast ballots, unique people or demographic turnout |
| Time and rates | Native November 4, 2026 date, absent clock/timezone; native election ID unqualified, analysis denominators/rates null |

The full **102-area 2026 Census contextual reference is byte-identical**.
Contextual FIPS are derived reference keys, not native source geography IDs.
No authority-boundary certification, city allocation, clipping or geometry
repair occurs. Both official authority-directory routes returned403 and remain
stopped; no alternate client, cache or mirror was used.

Release **439900272** targets source `09eff27`; all eight full assets were
anonymously verified before main activation. The ZIP is **1,102,066 bytes /
19 members**, SHA-256
`3e55e0f9b30ca7f1c326553133e7968b5a580661aad3e8da87ef747737e76bd4`.
It contains all **216 source queries, 204 context decisions, two frames and
204 contextual observations**, both full originals, full reference, code,
tests and results. **2,814 independent checks** and two exact network-blocked
reproductions pass. All 182 affected tests, Astro and full build pass.

Desktop/mobile verifies both modes/all102 counts, all six separate city
records, scope labels, Official exclusion, Methods and all51 navigation;
focused tests preserve native-zero priority. A real retry defect was fixed: recovery now restores source
selectors as well as the map. The original source tables/downloads remain.
Source `09eff27` is **live and actual-production verified**. Pages
`42747433131` attempt1 and guard `42747433393` succeeded; native artifact
`13731489436` passes **989,037,557 payload / 991,600,640 tar bytes**.
All **30 unqueried production files** match. Illinois102 desktop/mobile,
both modes/all counts, all six city records, scope rejection, restored retry
selectors, Official exclusion and Methods pass. Alaska81/Maine480/Hawaii4/
all51 navigation pass; all 436 old complete-download mappings survive.
The [source record](data/participation-access/20261110-illinois-county-context-01/observations.json)
and [acceptance](data/participation-access/20261110-illinois-county-context-01/website-acceptance.json)
retain the evidence. This does not qualify whole-county turnout or nationwide
native precinct completion.

## 2026 Alaska native geographic ballots: partial app reference

The [complete query supplement](https://github.com/hanshanley/margin_of_error/releases/download/voter-alaska-native-display-20261110-01/complete-analysis.zip)
joins held native geographic-unit **House `b` ballots**, not candidate selections,
to a partial unrepaired reference selected by the official **26GENR** app.

| Scope | Treatment |
|---|---|
| Complete counts | All 523 qualified records: 402 geographic, 120 pooled district and one federal-overseas; native ballot parent 215,906 |
| Partial display | 81 geographic units / 38,672 native ballots; all 321 other native shapes retain topology holds |
| Native paths | Independently confirmed longitude/latitude deltas; the 81 selected shapes each have one closed path per polygon, valid unrepaired geometry and no mutual interior overlaps |
| Reference qualification | Official 2026 election-app-selected display reference, not certified legal boundaries; no repaired locator substitution |
| Ballot modes | No assignment of pooled absentee/early/question or overseas ballots to residential precincts |
| Rates and clocks | All analysis denominators/rates null; native `11/04/2026 2:11 PM`, timezone unspecified, unofficial |

The **1,385,095-byte / 32-member** supplement retains all 402 shape decisions,
all 523 source-count queries, all 81 mapped observations and exact geometry,
six complete official originals, safe receipts, prior qualification inputs,
independent implementation, tests and results. Its SHA-256 is
`81952502eabda1a238b3a3c56e58dae39cac2fab2ce14390161202ecc683a7d2`.
Compiled publisher code, HTML credentials and acquisition headers are excluded.
No new count acquisition, candidate reduction, clipping or geometry repair occurred.

Source `3bba8bb` passes **176 affected JavaScript tests, four focused Python
tests, Astro and full build**, desktop/mobile exact81 values/source clocks/
Methods/state roundtrips/checksum failure and retry, and all51 navigation.
**10,055 independent checks**, all 9,309 selected source vertices and two
byte-identical network-blocked reproductions pass. All 436 old complete
download mappings remain byte-identical.

Immutable release **439872282** was published at **2026-11-10T02:21:48Z**.
All eight full assets were anonymously byte-verified before main activation.
Pages `42742241487` built successfully; artifact `13729439177` is retained.
The actual native artifact passes **989,017,669 payload / 991,580,160 tar
bytes**, 29 pinned files and the unchanged 436-download manifest.
Deployment attempt 1 timed out in `syncing_files` at the supported 600,000 ms
limit. **Attempt 2 succeeded**, retrying only the failed deployment and retaining
the exact artifact; no numerical source, release or successful build was repeated.
Source `3bba8bb` is **live and actual-production verified**: all 29 unqueried
files match, every mapped value passes on desktop/mobile, failed-source retry
works, and Maine480/Hawaii4/all51 navigation remain intact. Indiana83, Connecticut
169 and the other supported precinct/local layers pass the broad navigation
audit. All 436 old complete-download mappings survive. The machine-readable
[source record](data/participation-access/20261110-alaska-native-display-01/observations.json)
and [acceptance](data/participation-access/20261110-alaska-native-display-01/website-acceptance.json)
retain the evidence. This is partial native geographic-unit activity, not
nationwide precinct completion or a qualified full-election turnout rate.

## 2026 project: Maine partial locality activity

The [complete immutable query package](https://github.com/hanshanley/margin_of_error/releases/download/voter-maine-locality-activity-20261110-01/complete-analysis.zip)
connects held **civicAPI source activity**, not the Civic/NORC survey or certified
government turnout. Both separate early/returned frames retain all **584 native
regions**. Each has **480 one-to-one contextual identities**, while **104 native
regions and 48 of the full 528 reference areas remain held**.

| Selection | Treatment |
|---|---|
| Identity basis | 441 already-qualified 2024 identity links plus 39 unambiguous literal Twp/Plt name matches per mode |
| Historical data | Complete held identity export included; historical voting counts, rates and electorate stocks are never transferred |
| Ambiguity | Explicit Lincoln/Rangeley/Unity/Washington town links do not assign their ambiguous Plt/Twp counterparts by elimination |
| Measure | Sum literal source-category `votes` within one activity frame; preserve Other/Unknown/Unspecified and zeros, not candidate choice |
| Time | Native November 2, 2026 dates remain; collector 2026 context is not an independently qualified native election identifier |
| Geography | Full original 2024 municipality reference is byte-identical; not native FIPS, county totals or certified 2026 precincts |
| Missingness | Unmatched shapes remain unknown, not zero; selecting one clears previous detail rather than retaining stale counts |

All analysis denominators/rates and generic cast/unique-person claims remain
withheld. Modes are never added, source counts are not allocated to counties or
unorganized areas, and no new original or geometry acquisition occurred.

Release `439851515` targets source `f6a9e98`; **all eight full assets were
anonymously verified before main activation**. The ZIP is **665,845 bytes /
19 members**, SHA-256
`f597ea56a5a4f10184629a1d829710b993efe8cd6cbcc8c21bbb3eef3214d890`.
It contains **1,168 native queries, 1,056 reference decisions, two complete
frame decisions and 960 selected observations**, all sufficient original/
reference/identity inputs, code, tests and results. **11,438 independent
checks**, two exact network-blocked reproductions, 174 affected tests, Astro
and full build pass. Local desktop/mobile verifies every count/hold, both modes,
stale-detail clearing, failure/retry, CT169 and all51 navigation.

Source `f6a9e98` is **live and actual-production verified**. Pages `42738234318`
and guard `42738234642` succeeded; artifact `13727918651` has **988,975,450
payload / 991,528,960 tar bytes**, both strict limits passing. All 27 checked
unqueried production files match. Every mapped count and unknown area passes
on desktop/mobile in both modes, including stale-detail clearing, failure/retry,
CT169, all61 provider frames, native HI4/WV priority and all51 navigation.
All 436 older complete-download routes remain unchanged. The remaining default
contest-only fallbacks are AK/IL/MA/NH; Maine's partial local activity does not
establish county totals or nationwide native precinct completion.
See the [source ledger](data/participation-access/20261110-maine-locality-activity-01/observations.json)
and [actual acceptance](data/participation-access/20261110-maine-locality-activity-01/website-acceptance.json).

## 2026 Connecticut: native town counts, not county or precinct totals

The [complete immutable query package](https://github.com/hanshanley/margin_of_error/releases/download/voter-connecticut-native-towns-20261110-01/complete-analysis.zip)
reuses the held native **election 108**, explicitly identified as November 3,
2026. All **169 town VV cells sum to 1,150,127**; the separate native **Total
is not an extra town**. All eight numeric columns reconcile to that Total.
Native election-parent BC/RV, town EV, mode cells, printed TO and statuses remain
literal. Thirteen town PR cells are blank, not zero; a reporting counter does
not create 776 precinct observations.

| Scope | Treatment |
|---|---|
| Mapped count | Literal native town `VV`, not candidate choice or generic certified cast/unique-person counts |
| Other cells | EV, ABR/ABC, EBR/EBC, EDR/EDC and TO retained; mode/denominator definitions are not silently inferred |
| Geometry | All 169 names match the full held **2024 contextual municipality reference**, with original coordinates unchanged |
| Identities | Derived CT-TOWN IDs retain native town IDs and separate contextual reference keys; no invented FIPS or nine county totals |
| Time | Versions 52337/52338 have identical complete turnout payloads; tokens are not clocks, and retrieval is not a counting cutoff |
| Holds | All analysis rates/denominators remain null; no certified 2026 geography, mode sums or precinct allocation |

Release `439819338` targets source `5e8e75b`. Seven complete assets were
anonymously verified before main activation. ZIP: **175,231 bytes / 23
members**, SHA-256
`2793746307ae6aac600f515b7350196546fc9d6289bc97e1bf0b0531217b6030`.
It includes both native versions, complete town/Total queries, all eight
accounting checks, full original/derived reference inputs and offline code/tests.
**1,460 independent checks**, two exact network-blocked reproductions, 169
integration tests, Astro and build checks pass. Local desktop/mobile verifies
every count/raw cell, Methods, contextual year, bad-reference rejection/retry
and all 51 geographic interactions.

The town view is **live and actual-production verified** under workflow-only
successor `4d26889`. Pages `42735904153` and guard `42735903986` succeeded;
artifact `13727556269` has **988,726,858 payload / 991,283,200 tar bytes**.
All 25 checked unqueried production files match. Every native town count/raw
cell, desktop/mobile/Methods, bad-reference rejection/retry and all51 navigation
pass. All 61 provider frames, native Hawaii and West Virginia priority survive;
the 436-route complete-download manifest is unchanged.
The first Pages attempt built successfully but timed out during `syncing_files`.
Its action log confirms that `deploy-pages@v5` clamps the configured 1,800,000
milliseconds to 600,000; the earlier requested value did not establish a longer
effective window. One deployment-only retry retained artifact `13725048820`
but also timed out during syncing. The workflow-only successor `4d26889`
corrects the value to the supported cap, without changing numerical inputs,
the complete source package or Connecticut code. Its actual deployment and
production acceptance passed; do not repeat the successful build or release.
See the [source ledger](data/participation-access/20261110-connecticut-towns-01/observations.json)
and [actual acceptance](data/participation-access/20261110-connecticut-towns-01/website-acceptance.json).

## 2026 project: held county activity frames

The [complete immutable query package](https://github.com/hanshanley/margin_of_error/releases/download/voter-provider-county-frames-20261109-01/complete-analysis.zip)
connects already-held **civicAPI** activity, not the Civic/NORC survey or a
certified government turnout series. It preserves all **102 state/mode
decisions, 79 original responses and 6,371 regional queries**, including holds.
Exact complete county inventories and source-category parents qualify
**63 frames in 39 states / 4,731 county observations**. The reviewed Arkansas
`St Francis` spelling accounts for the two frames omitted by the initial review.
Two stronger official West Virginia frames keep priority, so the website uses
**61 provider frames in 38 states / 4,621 source-county counts**.

| Interpretation | Rule |
|---|---|
| Literal measure | Sum the native category `votes` cells within one early in-person or returned frame; not candidate choice |
| Time | Preserve October 23-November 4, 2026 source dates; collector election context is not an independently qualified native election identifier |
| Geography | Match full county inventories to separate 2026 Census references; do not promote towns, mixed jurisdictions or partial sets to county totals |
| Priority | Native positive and zero counts, including partial native snapshots, remain preferred; Best available uses one uniform activity frame only where native county counts are absent |
| Holds | All rates/denominators remain null; no cast/accepted/unique-person certification, mode addition, population allocation or fake intervals |

Original category buckets, colors, Other/Unknown/Unspecified and zeros remain.
Missing is not zero. All state-only, mixed, town and partial frames remain in the
complete queries; their `county_fips` is null, while `candidate_county_fips`
records only an unapproved name match. The one-second difference between
dataset directory `20261104T220424Z` and source snapshot `20261104T220425Z`
is preserved, not repaired. No original source was reacquired.

Release `439800051`, targeting source `5fc4f81`, has **seven complete assets
anonymously byte-verified before main activation**. The ZIP is **52,460,406
bytes / 144 members**, SHA-256
`0ef503144a4992f89cc541206f920dc02d038ab4a3eca4dfee06169d2b60b18a`.
It includes every sufficient original/reference, full CSVs, code/tests/results
and dependency-free reproduction. **71,197 independent checks**, two exact
network-blocked reproductions, 165 integration tests, Astro and build checks
pass. Desktop/mobile checks verify all 61 provider frames, native priority,
Methods and source rejection/retry; all 51 local geographic interactions pass.

Source `5fc4f81` is **live and actual-production verified**. Pages `42727767147`
and guard `42727766817` pass; artifact `13723313458` contains **988,580,213
payload / 991,129,600 tar bytes**, both strict limits passing. All 23 checked
unqueried production files match. Every provider frame/count passes on desktop
and mobile, alongside native Hawaii, West Virginia priority, rejection/retry
and all 51 geographic interactions. The 436-route complete-download manifest
is byte-identical to the accepted prior release. Production still has five
contest-only county fallbacks (AK/CT/IL/MA/NH) and no Maine county layer;
this is not nationwide native precinct completion.
See the [source ledger](data/participation-access/20261110-provider-county-frames-01/observations.json)
and [actual acceptance](data/participation-access/20261110-provider-county-frames-01/website-acceptance.json).

## 2026 Hawaii: four election administrations, five Census-county decisions

The [complete immutable query package](https://github.com/hanshanley/margin_of_error/releases/download/voter-county-hawaii-administrations-20261109-01/complete-analysis.zip)
reuses the held original reports: **Honolulu 228,487; Hawaii 62,453; Kauai 24,635;
Maui including Kalawao 50,324**, preserving the literal **TOTAL TURNOUT**.
Release `439767310` targets source `56c6252`; all six assets are anonymously
byte-verified. ZIP: 413,466 bytes / 24 members, SHA-256
`accb723320f22522ae6cd84206f0a84af11cd98fffb1745e8fd5fe26140a19bf`.

The [official counting manual, page 37](https://elections.hawaii.gov/wp-content/uploads/2024-Elections-Audit.pdf)
includes Kalawao in Maui for election reporting. Four reporting areas therefore
use four **administration IDs, not invented FIPS**, grouping the five complete
2026 Census county components. Maui/Kalawao polygons are united without clipping,
repair or count allocation. The download also preserves five separate
Census-county decisions: three single-component counts and **two held separate
Maui/Kalawao totals**. The map never duplicates 50,324 onto both counties.
These are derived reporting areas, not certified election-day precincts.

The original registrations, mail/in-person fields, printed sections and separate
November 4 REPORT 3 clocks remain; no timezone is inferred. All analysis rates
and denominators stay null, and TOTAL TURNOUT is not promoted to certified cast
ballots or unique people. State summary **365,897**, source-unit total
**365,903** and four separate administration snapshots summing **365,899** remain
distinct; the latter is diagnostic, not a researcher statewide control.
All 496 earlier unit observations and their missingness survive unchanged.

Source `56c6252` is **live and actual-production verified**. Pages `42721367937`
and guard `42721367517` succeeded; artifact `13721431268` has
**988,250,714 payload / 990,781,440 tar bytes**, both strict limits passing.
All 18 checked production files match the artifact. Every native area count,
desktop/mobile/Methods, invalid-component rejection/retry and all 51 geographic
interactions pass. All 436 old complete routes remain. The full package passes
51 independent member/value/union checks, two exact network-blocked query and
geometry reproductions, 160 focused/frozen/page tests, Astro and build checks.
See the [source ledger](data/participation-access/20261109-hawaii-administrations-01/observations.json)
and [actual acceptance](data/participation-access/20261109-hawaii-administrations-01/website-acceptance.json).

## 2026 Colorado: complete county returned-and-processed counts

The [complete immutable query package](https://github.com/hanshanley/margin_of_error/releases/download/voter-county-colorado-returned-20261109-01/complete-analysis.zip)
contains **all 64 county decisions**, the original aggregate workbook, all seven
worksheets' cells, three native county/party/mode frames, explicit state parents,
the full 2026 Census county reference, and offline code/results.
Release `439743253` targets source `944d846`; all six assets are anonymously
byte-verified. ZIP: 1,023,255 bytes / 16 members, SHA-256
`3551b8f7035000f047a1b9c98c19e521bb4cccd8c459b3263b26218e2fc5a9b1`.

The native **ALL RETURNED BALLOTS - MAIL AND IN PERSON COMBINED** parent is
**2,761,449**; separate mail and in-person parents are **2,618,985 / 142,464**.
The map uses the source's all-returned total, not a researcher mode sum.
These are **returned/processed**, not cast, accepted, counted, certified, final
or unique people. Source period: **11:59 p.m., November 5, 2026**; publication:
November 6; timezone absent. No county denominators are supplied, so all county
rates remain withheld. Native party categories are registration affiliation,
not candidate choices. Earlier November 4 provider modes are unchanged.

A separate exact-name review matches all 64 native county identities to the
complete, hash-verified **2026 Census** reference; no precinct map or geometry
repair is claimed. Independent OOXML/source review passes 612 checks, the full
package passes 402 further checks and two exact blocked-network Node/Python
reproductions, and 156 focused/frozen/page tests pass. Astro has no errors or
warnings; desktop/mobile checks verify every count, original mode record,
source clock, archive link and Methods roundtrip. Combined website source
`cb79d84` is **live and actual-production verified**. Pages `42717017978` and
credential guard `42717018339` succeeded. Native artifact `13717918487` is
**988,185,251 payload / 990,709,760 tar bytes**; both strict limits pass.
All 16 checked production files match the artifact, including CO/WV/IN/MD/MI
APIs, scripts and earlier archives. Every CO/WV native count, desktop/mobile
Methods and source recovery, and all 51 geographic interactions pass without
valid-source overrides. All 436 earlier complete routes survive. The
deployment-only successor changes the sync timeout, not numerical inputs or
the immutable release. See the [combined acceptance record](data/participation-access/20261109-county-modes-01/website-publication.json).

## 2026 West Virginia: separate county participation measures

The [complete immutable query package](https://github.com/hanshanley/margin_of_error/releases/download/voter-county-west-virginia-modes-20261109-01/complete-analysis.zip)
contains **220 county/mode decisions**, sufficient original workbooks/reports,
the full 2026 county reference, and offline code/results. Release `439728452`
targets website source `d0371e8`; all six assets are anonymously byte-verified.
The ZIP is 1,165,420 bytes / 25 members, SHA-256
`6c7656675b751b662162c29d0a282b667980c5412c1db707d7bc6fe1e2221c66`.

| Separate source frame | Qualified county scope | Meaning and limit |
|---|---|---|
| Independent November 3 ballot reports | Wood 22,935; Kanawha 48,729; Monongalia 28,614; other 52 counties held | Native **Ballots Cast**, separate clocks and unofficial snapshots, not a researcher statewide total |
| Early in-person workbook | All 55 counties; explicit source parent 162,349 | Source **TOTAL VOTERS**, early period October 21–31, not full-election turnout |
| Absentee-returned workbook | All 55 counties; explicit source parent 7,001 | Returned, not qualified cast or accepted ballots |
| Absentee-requested workbook | All 55 counties; explicit source parent 9,735 | Requests, download-only rather than a participation-map mode |

The official November 2 release declares all three workbooks. Preserve every
county/party cell, native zero, state parent and the empty extra worksheet.
The seven native party categories are **not candidate choices**; their
operational affiliation definition is unqualified. Never add modes or promote
the article's mixed-mode 169,350 figure to cast ballots. Native mode clocks and
timezones are absent; all analysis rates, denominators and unique-person claims
remain withheld. Monongalia's **0 complete / 43 partially reported** remains
literal, not repaired. No new precinct map is approved.

Independent workbook review passes 1,598 cell checks; the complete package
passes 687 further checks and two exact network-blocked Node/Python
reproductions. All 152 focused/frozen/page tests, Astro checks, local
desktop/mobile mode/value/Methods/retry checks and all 51 geographic selections
pass. The existing measure selector keeps early, returned and all-method frames
separate; an incomplete selected mode is rejected rather than silently replaced.
Native artifact `13716648981` passes exact source/API checks and both strict
limits: **988,163,667 payload / 990,689,280 tar bytes**. Pages `42713872385`
built successfully but timed out during file synchronization; a deploy-only
retry was cancelled. No successful build, archive or source acquisition was
repeated. Source `cb79d84` combines this unchanged integration with Colorado
and increases the deployment sync window. The successor is now live: its
actual artifact, unqueried production bytes, both native views and all-state
interactions pass as recorded above. The default WV all-method frame still
has only three county counts; early/returned completeness is not full-election
turnout completeness.

The [access ledger](data/participation-access/20261109-west-virginia-modes-01/observations.json)
records the full 55-county query, directory-identity problems and six stopped
state/county results products. Denials are not retried through another client,
cache, mirror or app-data endpoint. Independently published originals supplied
the counts; no candidate-vote substitution or geographic allocation was used.

## 2026 Indiana county statistics and Monroe reporting units

The [complete immutable source package](https://github.com/hanshanley/margin_of_error/releases/download/voter-county-indiana-voter-statistics-20261109-01/complete-analysis.zip)
contains **93 original statistics rows, 92 county decisions, all 24 independent
county follow-ups and all 103 Monroe reporting-unit counts**. It is
28,598,360 bytes / 133 members, SHA-256
`a8afc335f530edf0bf60e76eeed71a3f416de19df41629d0192689be2757a30a`.
All eight complete assets are anonymously byte-verified; release `439670388`
is immutable and targets website source `9377b8c`.

The official `statewideTurnout_B.json` supplies 68 positive **VotersVoting**
counts. Its 24 zero records conflict with positive native Secretary of State
votes: retain every original zero, withhold the contradictory selected value,
and never replace it with candidate votes. Seven independently reviewed
county snapshots raise usable county counts to **75 of 92**, with **17 held**.
Cass/Fulton are literal native turnout numerators, not cast ballots; the other
county snapshots retain their ballot labels and separate source clocks/status
conflicts. LaPorte's undefined PUBLIC COUNT remains held.

The original state subtotal **1,055,902** stays unchanged and partial, not a
mixed-source statewide turnout estimate. Statistics clock
`2026-11-09T15:03:29.353`, candidate-control clock `15:03:39.467` and settings
clock `15:04:55.92` are separate November 9 native clocks with no timezone.
InPerson/Absentee keep their definitions; Absentee is not mail received.
All analysis denominators/rates and unique-voter claims remain withheld.
County identities use the complete, hash-verified **2026 Census** reference,
not the source application's default 2013 map.

Monroe's publisher-defined **Total Ballots Cast** indicator is **42,766**.
All 103 native rows and raw registration/percentage/status fields survive.
Only **83** nonoverlapping official-app current-reference polygons are mapped;
the federal carrier (241 ballots) and 19 overlapping split polygons stay
table-only. No clipping, repair or count allocation. Every row says
Partially Reporting; source clock is absent and copied primary-instruction
text conflicts with the general-election heading/service. The app-selected
reference is not independently certified election-day legal geography.

The archive includes sufficient permitted originals, full reference inputs,
all queries/holds, numerical controls, evidence and offline code/results,
excluding compiled dashboard code, contacts and acquisition session headers.
4,425 independent checks and two exact network-blocked reproductions pass.
146 focused/page/frozen-reader tests, the full build, Astro checks,
desktop/mobile native-value/retry checks and all 51 geographic interactions
pass locally and on **actual production**, without valid-source overrides.
Website `9377b8c` is live and accepted: Pages `42703763791` and credential guard
`42703763711` succeeded. Native artifact `13712737717` contains
**988,132,436 payload / 990,658,560 tar bytes**; both strict limits pass.
Every new script/pointer/reference, IN/MD/MI generated API and prior complete
archive matches production. The only local/generated-gzip difference is the
platform-header byte; every decompressed JSON byte matches. All **436 earlier
complete routes** and the short, default-closed Methods survive.
This adds partial Indiana coverage, not statewide completion or nationwide turnout.

The [source-access ledger](data/participation-access/20261109-indiana-expansion-01/observations.json)
retains the two stopped Indiana script routes and four unsuccessful filename
queries, Tennessee/New Hampshire/Kansas denials, the governor-vote proxy
exclusion, and West Virginia's declared general-results verification challenge.
No other-client/cache/mirror retry, challenge solving or cached number promotion.
These access records are not a numerical download; the complete numerical
release is linked above. Independently declared county publications remain
separate legitimate leads.

## 2026 county source counts: Maryland and Michigan

Website `51f8010dd5f030bcec5d922f519f62031bb74ed3` is live and verified:

| Source scope | Displayed count | Retained limits |
|---|---|---|
| All 24 Maryland county-equivalents | Native **Cards Cast**, not qualified cast ballots or unique voters | November 8, 2026, 7:44 p.m.; timezone absent; every analysis rate/denominator withheld |
| Bay and Isabella, Michigan | Explicit native ballot parents: 50,246 and 26,288 | Other 81 counties missing; all 63 earlier unit rows unchanged; rates withheld |

Both use separately checksum-verified full **2026 Census county references**,
not certified precinct boundaries. Baltimore city and county remain distinct;
Saint Mary's / St. Mary's has one explicit alias and unchanged native labels.
Maryland's MIB2 title, 25 county/state records, native Eligible Voters/percentages
and non-precinct reporting counters survive. Michigan retains Bay's 43 reporting
counter versus 35 report sections and Isabella's 22-ballot election/House-scope
difference. No candidate votes, state estimates or pooled ballots are allocated.

The [complete Maryland download](https://www.themarginoferror.com/participation-county-cards/20261109-01/complete-analysis.zip)
is **633,225 bytes / 17 members**, SHA-256
`11c81fc255f2203ae513a125d7e9151e25277cdafdb7c1b65f832b389a5ebeb6`;
[Michigan's complete download](https://www.themarginoferror.com/participation-county-parents/20261109-02/complete-analysis.zip)
is **2,937,769 bytes / 38 members**, SHA-256
`75140de431911ad17635399c7b1fada2c57353cabbbff0622c4b4ed42652f68c`.
Both retain sufficient originals, every query/hold, full references and offline
code, not metadata-only. The frozen default reader and old archives are unchanged.
139 focused/page/context tests, four build tests, Astro checks, exact offline
reproductions, desktop/mobile native-value/retry checks and all 51 geographic
selections pass locally and on actual production. Pages `42687510890` and
source-check `42687510495` succeeded. The actual downloaded native artifact
`13706930410` contains **987,714,304 payload /990,238,720 tar bytes**.
Committed scripts, both complete archives, generated MD/MI data and the unchanged
436-route manifest match production. The two generated gzip files differ from
macOS only in their platform-header byte; every decompressed JSON byte matches,
and production's compressed files match the Linux artifact exactly. No valid
source was overridden in the native-value acceptance checks.

The [source-access ledger](data/participation-access/20261109-whole-state-county-01/observations.json)
and [complete 88-county Ohio query dispositions](data/participation-access/20261109-whole-state-county-01/ohio-county-report-queries.json)
record zero new numerical inputs. All 88 candidate report routes returned403;
their existence/publication scope was not established. Ohio/New York statewide
roots and the Michigan dashboard are stopped, and the declared South Carolina
general-results link reaches a verification challenge. No other-client/cache/
mirror retry or cached numerical promotion is allowed. Texas's accessible
candidate-table "Ballots Cast" column and the New York governor-vote proxy are
not full-election participation. These are access records, not an analysis release
or substitutes for complete numerical downloads. That deployment's audit found
20 states with contest-only county fallbacks; Indiana above reduces the current
number to 19. Maine still has no county layer.
Other source-count states can have only one or two counties; Maryland cards are
not unique-voter coverage. Nationwide county/precinct participation stays open.

## 2026 source-unit counts: accessible without invented maps

Website `a218d8266b597de7eede26b7f3c24d6bdcb056a4` exposes all **523 Alaska**
and **496 Hawaii** reporting units in the precinct view, with search, selection,
native counts, source clocks and complete original downloads. Pooled, federal,
overseas and VSC units stay distinct. Hawaii's six-ballot source discrepancy
and zero VSC registration fields remain unchanged. No rates or boundary joins
are enabled. Pages `42666789732` succeeded; exact production script/index,
desktop/mobile source checks and all 51 geographic interactions pass.
Native artifact `13696424148`: **983,885,957 payload /986,398,720 tar bytes**.

Website `23f0a33cf83a865e37cdb4b81161d4884ae0ed11` additionally exposes all
**4,963** already-held native CSV rows for Arizona, Arkansas and Wyoming,
including **83 missing ballot totals**, every original field and real zeros.
All 19,852 independent field checks pass. No statewide/all-mode total, registration
denominator or old boundary substitution is inferred. Pages `42670805978`
succeeded; native artifact `13699406690` contains **984,124,912 payload /
986,644,480 tar bytes**. Exact production script/index, all 5,982 desktop/mobile
unit IDs and edge cases, full download links, checksum rejection/retry and
51-jurisdiction geographic selections pass. This adds count access, not precinct maps.

## D.C. and Virginia precinct maps: live verified

Website `965fbc2` includes the existing **144 native D.C. precinct** ballot
and registration observations to the reference already selected by the official
2026 app. Fractions remain provisional election-night shares, not final,
population or demographic turnout. The app's 2019-named reference attribution,
withheld overlapping strips, whole-precinct counts, native clock and complete
original ZIP remain explicit. Every native value, desktop/mobile state-sidebar
navigation and retry checks pass on the actual production site.

It also exposes **710 Virginia precinct** native `ballotsCast` counts, including
260 where the distinct `voterTurnout` field differs. Every value, label,
registration field and native UUID join independently matches the held locality
originals. The browser checks the compressed map checksum before decoding and
withholds every rate. No source was regenerated or replaced; all 1,819 exclusions,
separate source clocks, current-reference attribution and complete original ZIP
remain intact. Current references are not certified election-day boundaries.

The integration passes 36 focused tests, four build tests, Astro checks,
desktop/mobile checks of all 854 new map values, checksum failure/retry and the
51-jurisdiction production browser sweep. Pages `42675737057` succeeded.
Actual downloaded native artifact `13701385628` contains **984,130,264 payload /
986,644,480 tar bytes**; its scripts, source pointer, full new CSV inputs,
native-county archive and all 436 complete-download routes match the reviewed
bytes. Exact production scripts/pointer and every new native value pass without
source overrides. Old IDs, links and the short Methods overview survive.
Earlier D.C. runs `42673645311` and `42674283986` failed inside GitHub before
building; the combined deployment supersedes those failures.

## 2026 native county parents: live geographic integration

Website `269406570805a8f9a030f4f01d1ff49f608cc9d5` connects held official
county parents rather than inferring turnout from House candidate votes.

| Source | Native county ballots | County queries | Analysis fractions |
|---|---:|---:|---|
| Idaho, November 4 county snapshots | 731,980 | 44 | 43 source-registration fractions; Twin Falls held |
| North Dakota, native v75 / November 5, 2026 UTC | 239,057 | 53 | All withheld; API field is not promoted to registrations |

Idaho's explicit `ballotsCast` parents independently match the original
ballot-report workbook. Twin Falls retains the 42,990 county/API versus
41,878 workbook registration disagreement. North Dakota's `TotalBallotsCast`
parents reconcile to its independent turnout API, all 358 unit observations
and state parents; explicit zero buckets are not replaced by missing-as-zero.
All 986 Idaho and 358 North Dakota unit rows and existing precinct holds remain.
Complete state/county identities and compressed **2026 Census reference**
hashes are checked before mapping; these are not certified precinct boundaries.

[Complete 97-query sufficient-input download](https://www.themarginoferror.com/participation-county-parents/20261109-01/complete-analysis.zip):
**2,513,817 bytes /21 members**, SHA-256
`0ada1f2fd2657d00a30b53e323ecc320adf2ab75b74880a3a0e4ca49e921d915`.
It contains all 43 selected/54 held queries, sufficient original inputs,
reference geometry and a dependency-free offline reproduction. 280 independent
checks, two exact reproductions, 131 tests and live desktop/mobile/all-state
browser checks pass, including rejecting corrupted geometry and successful retry.
Old contextual exports reproduce through the unchanged legacy reader; the live
reader explicitly opts into the new parents. No original counts or earlier
archives were replaced. Native artifact `13696510311` has **983,878,341 payload /
986,388,480 tar bytes**, with all 436 old complete-download routes preserved.
Broader county/precinct and demographic evidence gaps remain open.

## 2026 source-reported already-voted profiles

[Complete reported-stage study](https://github.com/hanshanley/margin_of_error/releases/download/participation-civic-reported-stage-20261109-01/complete-analysis.zip)
reuses the verified private LVB reduction without repeating original
survey acquisition/reduction. All **306 overall/age profile decisions**
and **612 stage-cell queries** include 182 holds.

| Selected source profiles | Count |
|---|---:|
| Statewide | 46 |
| State/age | 78 |
| Total profiles across 49 source states | **124**, not 124 states |

Native **LVB5, Already voted** is a labelled response, not an
administratively verified ballot. The **opaque other/unresolved** block
combines future voting intentions, explicit nonintentions and unknown/
skipped/refused responses; it is **not nonvoting or staying home**.
Unknowns remain in full source denominators. Field period, common
interview cutoff and weight target/calibration remain unqualified:
these profiles are not a timestamped early-vote curve or population turnout.

Existing public-parent selection, n100 parents/n30 positive stage cells,
small-difference guards against published model margins and age-complement
checks apply. One extra whole-age-profile hold protects complements.
Held stage counts/weights stay NULL. No separate native1/2/3/4/99 masses,
pooled/national profile, individual LVB/model intersection, party fitting
or prior-voter cohort restriction. All prior-response categories were summed.
All 1,530 model-query bytes, native28, age-register study and website survive.

Sixteen tests, **20,712 independent checks** and two exact offline
reproductions pass. Immutable release `439297970` has eight full
byte-verified assets. The **308,015-byte / 13-member ZIP** includes complete
permitted numeric stage primitives/masks, full public parent inputs,
definitions, preserved queries, safe receipts, standard-library extraction/
analysis code/tests and every query/result. Private fine reductions,
respondent identifiers and denied app bodies are excluded. SHA-256:
`a5d3f21a799a02635b73b229172f0111344cf1950e615cc52b993c5514a4c314`.

**Distinct access follow-ups:** the
[two-observation ledger](data/registration-access/20261109-09/observations.json)
records Ohio's primary-certification announcement403 (1,253,339 bytes) and
Iowa's primary-results index403 (5,558 bytes). Both routes stopped without
another client/cache/mirror or cached count promoted to analysis.
The old Ohio aggregate portal was not retried. Broader independent
administrative demographic/precinct participation gaps remain open.

## 2026 same-age registration-frame source units

[Complete age-frame study](https://github.com/hanshanley/margin_of_error/releases/download/participation-age-register-frames-20261109-01/complete-analysis.zip)
answers a new, bounded question using already-held native stocks and
already-qualified public Civic model weights. All **255 state/age decisions**
are retained: one conditional SC 65+ scenario and 254 holds, not nationwide
observed age-group turnout. Other states have no native age frame selected
in this package; this is not a claim that no such source exists.

| SC 65+ reference | Source quantity |
|---|---:|
| Derived registered stock: Female + Male + Unknown gender | 580,268 + 465,059 + 150 = **1,045,477** |
| Civic source cases, native model classes | 553 cases; 518 / 35 |
| Source-weighted native model participant share | 98.41966473% |
| Conditional participant / nonparticipant source units | **1,028,954.96 / 16,522.04** |

The register is RP0040 / Race:All / statewide TOTAL, cells N58/T58/AA58.
Its age total is **derived, not a printed parent**; Unknown gender is
included without mapping administrative gender to Civic sex. November 2,
2026 is the report label, not a known cutoff, age-reference day, clock or
timezone. Status, survey field period and population/age-clock
exchangeability remain **UNVALIDATED**. Compatible 65+ boundary labels
do not establish full construct or population equivalence.

This uses the matching state/age group's own full propensity, not statewide
or pooled probability allocated to a group or locality. No observed voters,
staying home, ballot residual or design interval is inferred. CA 66+ is not
65+; other native bins are not split, unknown/held cells are not recovered,
and no under-65 complement or statewide age-standardized total is supplied.
All 1,530 previous model queries and native28 references remain byte-identical.
No new acquisition, completed native/survey campaign or website build.

Fifteen tests, **1,963 independent checks** and two exact offline reproductions
pass. Immutable release `439239428` has nine full byte-verified assets.
The **491,844-byte / 18-member ZIP** includes original SC and CA age
workbooks, independent snapshot/provenance, complete public Civic weight
primitives, preserved reference queries, source scope, standard-library
code/tests and every new query/result. SHA-256:
`4fef5edd5ea6c874e5fbf60faef619e578f95ce69036a7cab2bd7c5be1820ce1`.
Broader independent demographic/precinct participation gaps remain open.

## Maryland dated registers and unofficial card references: native28

[Complete native28 package](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-28/complete-analysis.zip)
adds three exact, declared Maryland general-election statistical originals.
Both indexes and all originals returned HTTP200. The distinct, stopped
October monthly-registration PDF was not retried.

| Native reference | Count | Source clock |
|---|---:|---|
| ACTIVE precinct register | 4,293,322 | As of October 18, 2026 |
| INACTIVE precinct register, kept separate | 283,680 | As of October 18, 2026 |
| UNOFFICIAL Cards Cast | 2,079,801 | Run November 8, 2026, 7:44 p.m.; timezone unspecified |

All 350 registration-party count cells, 25 card references and 66 accounting
rows are retained. Every 24-county sum reconciles to its printed parent.
The card report's 4,293,322 Eligible Voters match the active roster and
give the displayed 48.44% reference: same-agency corroboration, not
independent population validation. Registration stocks are **not
participation by party**; cards are not certified unique voters/ballots.
Reporting counters are not precinct records or final-canvass certification.
The actual title includes MIB2 despite the index/election-night filename.
A web preview showed an older November 2 zero snapshot; the exact archived
PDF was rendered locally and matches the November 8 counts. No preview or
cached count supplied numerical input.

One unchanged statewide Civic propensity transported to the ACTIVE frame
yields 2,315,995.67 participant / 1,977,326.33 nonparticipant **source units**,
with UNVALIDATED date/status/registry-frame exchangeability. No inactive/SDR
addition, staying-home/card-minus-model residual, group/local model
allocation, eligibility certification, interval, rate/map or website view.
All 50 other states, 51 prior dispositions and 33 scenarios remain exact;
native28 has 51 state/D.C. rows, 52 dispositions and 34 scenarios, not 34 states.

Fourteen tests, 4,006 independent checks and two exact offline reproductions
pass. Immutable release `439195403` has nine full byte-verified assets.
The **106,571,158-byte / 17-member ZIP** includes the originals, safe receipts,
independent grids, accepted Civic parent, complete native27, code/dependencies,
tests and every query/result. SHA-256:
`74cf1dd932be643b8a408c0fbfbd9d589297e07363c242e817a0c7be1af987fe`.
Broader independent demographic/precinct participation gaps remain open.

## Every-state CPS frames across four elections

[Complete 2018/2020/2022/2024 package](https://github.com/hanshanley/margin_of_error/releases/download/participation-cps-four-year-frames-20261109-01/complete-analysis.zip)
adds newly acquired, exact declared Census originals for 2018 and 2020.
All fifty states and D.C. have **3,468 state/year/group queries** covering
citizen and registration-supported respondent frames. The 1,734 accepted
2022/2024 registered queries and rates are reused exactly; their entire
original query is included byte-for-byte, not re-estimated.

All **1,734 same-election-type comparison decisions** cover 2018-to-2022
midterms and 2020-to-2024 presidential elections. Three registered-frame
comparisons and one citizen-frame comparison remain held for missing
endpoints. Differences are source-specific percentage-point arithmetic,
not harmonized population turnout change, causal effects or matched-person
retention. Weight targets and response subclasses are not harmonized.
No new/returning-voter, deaths/migration/eligibility or 2026 population
projection; sparse flags are not precision guarantees.

The older native layout is different: 1,018-character records, PES1 at
1001-1002 and PES2 at1003-1004, without PRSUPINT. Native `-9` remains
undistinguished no response, not an invented noninterview flag.
The 2018 questionnaire's literal `November X, XXXX` placeholder is
preserved; year/month come from the index and actual records.
Unknown registration stays separate; voting unknowns within supported
registered frames remain in the full denominator. Source registration
support is not independently validated registry membership or eligibility,
including for North Dakota.

All 13,731 new coarse pairs, 5,202 registration-class rows, 6,520 exclusive
partition checks and 204 original-cell CPS comparisons are retained.
Fifteen tests, **550,090 independent checks** and two exact offline
reproductions pass. Immutable release `439157433` has ten full
byte-verified assets. The **10,207,451-byte / eighteen-member ZIP**
includes complete sufficient aggregates, original codebooks/references,
the complete earlier package, receipts, code/dependencies, tests and every
query/result/checksum. Raw survey records and identifiers remain local.
SHA-256: `cbff5470e9153e38095859413a9ad379f535021cbcb172282982b5596e868d69`.
Native27, existing 2026 models, earlier releases/access holds and website
remain unchanged; no new rate/map/view.

## 2026 model classifications by recalled prior-contest response

[Complete nonpartisan classification package](https://github.com/hanshanley/margin_of_error/releases/download/participation-civic-history-classifications-20261109-01/complete-analysis.zip)
reuses the verified Civic joint reductions without rerunning the survey
reduction or model campaign. All 102 current-state/prior-contest decisions,
408 cell queries and 204 conditional-rate queries are retained:
**77 supported tables** (33 recalled 2022 House / 44 recalled 2024
presidential) and 25 holds including D.C. absence, not 77 states.

The prior blocks are recalled candidate choice, including Other candidate,
and an **opaque other/unresolved response** block retaining explicit
no-prior-contest-vote and unknown responses together. The latter is not
classified prior nonvoting. Neither component is separately disclosed or
imputed. Current candidate-choice unknown remains a model participant
when the native model says voter. No party-choice table is released.

These are classifications within the 2026 source frame. Its state is not
verified prior residence; its weights are not the 2022/2024 population.
No historical turnout, original-cohort retention, first-ever/new/returning
voter population, staying home, eligibility or geographic allocation.
Each selected parent has at least100 cases; each positive coarse cell
has at least30. Whole unsupported tables stay null, with complementary
state holds. All fifty current model parents remain exact across both
prior contests, giving 100 preservation checks.

Fifteen tests, 4,652 independent checks and two exact offline
reproductions pass. Immutable release `439121934` has seven full
byte-verified assets. The **67,954-byte / fourteen-member ZIP** includes
all permitted sufficient coarse inputs, code, tests, every query/result,
source contract/receipts and checksums; no private fine cells or raw records.
SHA-256: `1fcbcc597323158d7c92b7b3022fbf8926f876305e1ca3f82d214940d5949dcc`.

[New York reporting receipt](data/registration-access/20261109-08/observations.json)
records actual403 / 5,462 bytes from the distinct HomeNoJS product.
That route is stopped without alternate client/cache/mirror or promoting
a cached search count; the older November1 workbook hold also remains.
No New York registration denominator is added. Native27, prior models/
releases/holds and website remain unchanged; no new rate/map/view.

## Every-state CPS registration-supported demographic participation

[Complete 2022/2024 package](https://github.com/hanshanley/margin_of_error/releases/download/participation-cps-registered-groups-20261109-01/complete-analysis.zip)
adds a distinct registration/voting joint analysis, not a repeat of the
citizen-frame calculation. All 50 states and D.C. / 1,734 state/year/group
queries include **1,731 supported conditional estimates**, three empty
frames and 383 under-30 registered-case diagnostics.

The native question routing matters: PES2 is asked when PES1 is
`2,-2,-3,-9`. The registration-supported frame therefore includes reported
voters routed out of PES2 **or** explicit PES2 registration-yes responses.
Voters' routed `-1` is not nonregistration, and not every member directly
answered registration-yes. Noninterviews and unknown registration remain
separate. Unknown voting among frame members stays in the full denominator;
known-voting-response-only percentages are separate diagnostics.
These are source-conditional self-reports, not independently validated
registry membership, administrative turnout, staying home or 2026 projections.

All 13,624 coarse native response pairs, 5,202 registration-class rows,
11,896 exclusive-partition checks and 102 same-source published CPS
registration comparisons are retained. All 1,734 accepted citizen-frame
case/weight/outcome totals remain exact. Sparse flags are not precision
guarantees; no design interval or local/group population allocation.

Fifteen tests, 234,228 independent checks and two exact offline
reproductions pass. Immutable release `439088807` has nine full
byte-verified assets. The **5,097,068-byte / seventeen-member ZIP**
includes complete sufficient coarse public aggregates, Census codebooks
and native reference originals, code/dependencies, tests and every query.
No raw respondents, survey identifiers or private fine cells are redistributed.
SHA-256: `94da447edd1217ed07fc04eb996332ad322a699ceb7674d276de5e445a4bdbfb`.

[New source observations](data/registration-access/20261109-07/observations.json)
hold Louisiana's context-only election facts and unresolved environment
parish-registration embed without guessing a host. Nevada's independent
news route returned **HTTP200/challenge**, not403 or a statistical original:
stopped without challenge execution, alternate client/cache/mirror or
cached numbers. Full contact/app/challenge bodies stay local.
No zero voters/global absence inferred. Native27, prior models/releases/
access holds and the accepted website remain unchanged.

## Mississippi multiyear registration frames and conditional signals

[Complete 2022/2024/2026 package](https://github.com/hanshanley/margin_of_error/releases/download/participation-mississippi-register-history-20261109-01/complete-analysis.zip)
adds the exact declared October 2022 and 2024 reports, reusing the completed
2026 inputs unchanged. Derived all-82-county ACTIVE stocks are **1,926,538 /
1,965,611 / 1,888,362**, respectively. None is a printed statewide parent
or independent benchmark; actual cutoff/day/clock/timezone remain unknown.
Three registration-stock comparisons are not turnout, retention, new
voters, migration, deaths, eligibility or demographic change.

Two historical scenarios multiply October active stock by each year's
published CPS CVAP voted-to-registered percentage ratio: **46.4/72.6 in
2022**, **68.9/81 in 2024**. Rounded marginal ratios are not individual
registered-voter joints. Date/status/registry/population transport is
**unvalidated**; complements do not identify reported nonvoters or
unknown responses. Decimal arithmetic does not supply sampling precision.
The existing 2026 Civic model is a different measurement, reused exactly.
All nine year/source decisions and three held model comparisons remain
explicit; even the 2022-to-2026 midterm pair is not a validated turnout trend.

All nine pages / 246 county rows / 984 factual cells / 492 counts / 246
percentages are retained, including eight percentages above100.
CVAP vintages/headers/asterisks stay native, never a model denominator.
Layout-aware extraction preserves 2024's split Carroll text; original
2022 cross-reference warnings and bytes are not silently repaired.
Independent coordinate readers and original CPS cells agree.

Nineteen tests, 4,433 independent checks and two exact offline reproductions
pass. Immutable release `439058337` has ten full byte-verified assets.
The **1,706,238-byte / seventeen-member ZIP** contains every sufficient
original, public aggregate, complete original CPS package, code, test,
query/result and checksum, without unrelated nested baselines. SHA-256:
`5c4c69a370715d8e758ede707da7cb1bfc374b8de8173bb394715acbc772c17e`.
No private reduction or successful 2026 acquisition/recovery was repeated.
Current native27 controls, prior releases/holds/models and the accepted
website remain unchanged; no group/local allocation or new rate/map/view.

## Mississippi October active-registration frame

[Complete version-27 analysis](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-27/complete-analysis.zip)
adds the [official October report](https://www.sos.ms.gov/sites/default/files/active-voter-count-reports/2026October%20Voter%20Count%20Red.pdf),
selected from its declared active-voter-count index. The **1,888,362**
active registrations are our derived sum of all 82 county rows, **not a
printed statewide parent or independently benchmarked total**. October
comes from the index label; actual cutoff/day/clock/timezone remain unknown.
The index's general first-Monday policy is not an observed cutoff.

One separate scenario applies the full 1,443-case state Civic propensity
to that active stock: **928,335.68 participant / 960,026.32 nonparticipant
source units**, under **unvalidated** date/status/registry-frame transport.
These are not observed people, staying home, general ballots or legal
eligibility. No matched ballot residual, calibration or local/group allocation.

All three pages / 82 counties / 328 factual cells / 164 counts / 82
percentages are preserved. Independent text and word-coordinate readers
agree. CVAP mixes native 2023 ACS 5-year and thirteen asterisked 2020
Census references; it is context, not the model denominator or turnout.
Three percentages above 100 remain unclipped, not evidence of illegal
voting or fraud. All percentage-rounding diagnostics pass.

Fourteen tests, 2,384 independent checks and two exact offline reproductions
pass. All fifty other state rows, fifty prior controls and 32 scenarios
survive: now **51 state/D.C. decisions, 51 dispositions and 33 scenarios**,
not 33 states. Immutable release `439034403` has ten full byte-verified
assets. The 106,402,266-byte / seventeen-member ZIP includes the original,
sufficient independent inputs, complete version26 baseline, code, tests
and every query/result. SHA-256:
`92b66d3881d87b2742309eeec5d0bdd176170ba4e4b64f87cda580ec964b42bb`.

[New access observations](data/registration-access/20261109-06/observations.json)
distinguish New Hampshire's homepage403 (route stopped) from Illinois's
declared totals page **HTTP200/application error**, with no numerical input.
Neither establishes global data absence. Full error/contact/app bodies
remain local; no alternate client/cache/mirror or guessed parameters.
All prior releases, survey/provider models, source holds and accepted
website remain unchanged. Broader demographic/precinct evidence gaps stay open.

## Indiana primary-register context, not a November population

[Complete version-26 controls and original](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-26/complete-analysis.zip)
add the [official 2026 primary workbook](https://www.in.gov/dA/21e5da4ae7/2026-Primary-Registration-and-Turnout-Data.xlsx?language_id=1),
selected from its declared registration/turnout index. It reports
**4,713,746 Registered Voters in a PRIMARY context**, not a qualified
November general-election stock. The title does not establish a
registration cutoff, day, clock, timezone or active/inactive status.

One separate scenario applies the general-election Civic source-model
propensity to this primary registered stock: **2,061,059.39 participant /
2,652,686.61 nonparticipant source units**. Cross-election registry-frame
exchangeability is **unvalidated**. These are not observed people,
staying home, legal-eligibility certification or validated November counts.
Native primary **Total Voters 807,059 / Election Day 553,110 /
Absentee 253,949** remain context only: never November ballots,
general-model validation/calibration or a matched model residual.
Absentee is not independently qualified mail-only.

All 92 counties plus Statewide / 665 grid slots / 372 counts / 186
percentage fractions are preserved. All 97 component/county equations
reconcile. Twenty-seven stored percentage lexemes have binary artifacts;
their raw values remain exact, peer percentage comparisons use numeric
semantics, and the declared `0%` format supplies whole-percent displays.
Voter-count comparisons remain exact. All 186 rounding diagnostics pass;
rounding granularity is not a confidence interval. No missing/zero count
cells in this source; no formulas executed or percentages repaired.

Thirteen tests, 6,164 independent checks and two exact blocked offline
reproductions pass. All fifty other state rows, 48 controls and 31
scenarios survive; now **51 state/D.C. rows, 50 dispositions and 32
scenarios**, not 32 states. General ballot/rate/residual fields remain
null, with no local/group allocation or new rate/map/website view.
Immutable release `439007659` has eleven full authenticated-draft/
anonymous-published byte-verified assets. The 106,031,433-byte /
eighteen-member ZIP includes the entire original, independent grid/
formats, typed primary/general scope, receipts/discovery observations,
complete version25 baseline, reader/extractor/shared code, tests, every
query/result and checksums. SHA-256:
`32d68a849e97d834272e3813a736c2bdbb2157bfe3d62e960d7195acd643772e`.

[Illinois discovery receipts](data/registration-access/20261109-05/observations.json)
record two HTTP200 navigation pages without a selected numerical report.
This is not403, paid-only qualification or global data absence.
No voter-file purchase, personal records or guessed statistics filename.
The older Indiana county-count link explicitly says2025 and is not
relabelled2026 or used here. Provider-frame downloads, earlier releases,
all survey models, official403 holds and the accepted website are unchanged.

## Provider partial demographic counts and own-frame compositions

[Complete source-frame arithmetic package](https://github.com/hanshanley/margin_of_error/releases/download/participation-provider-demographic-frames-20261109-01/complete-analysis.zip)
reuses the held `20261109T083731Z` CivicAPI early-vote capture:
**408 state/mode/dimension decisions**, all **511 group/held rows**,
and **135 source-native group counts in 32 demographic views / 11 states**.
The API count feed is not the supplied Civic survey, and these are
**compositions within reported frames, not group turnout rates**.
Native source dates October 31-November 8 differ from the November 9
collector retrieval. Election context is collector-defined, not an
independently qualified native election identifier.

Each percentage uses its **own demographic-response total**, retaining
Unknown/Undesignated labels and all twelve source zero counts. Twelve
views differ from their mode totals: for example, Colorado age counts
are lower by 7,211 early / 664 mail units; Georgia early race differs
by 86,201. Signed discrepancies and dates remain explicit, not repaired
or imputed as unknown people. Twenty views have matching dates/totals;
that arithmetic does not validate equivalent populations or coverage.
No native-bin harmonization or pooling across modes, dimensions or states.

All 51 jurisdictions remain in the query. The provider's four capability
404s for AL/DC/MA/NH are source-specific absences, not zero voting or
data absence everywhere. All 376 held scopes have no invented groups or
statistics. There is no matched group registered/eligible denominator,
accepted/cast/unique-person certification, group or full-election turnout
rate, survey projection, causal/retention estimate or fabricated interval.
Official state403 holds remain stopped; provider counts are not substitutes
for independent official benchmarks.

Twelve tests, 13,997 independent checks and two exact blocked offline
reproductions pass. Immutable release `438975418` has six full
authenticated-draft/anonymous-published byte-verified assets. The
74,355-byte / eleven-member ZIP includes an 86-member sufficient-input
archive: all 83 raw capability/demographic responses, 79 unlabeled
native mode-parent vectors, reused reduced captures and original
byte/hash/clock/source provenance; plus reader/freezer, tests, every query/
result and checksums. County regions, party labels/colors, web bodies
and personal records are excluded. No new acquisition or completed
collector campaign rerun. SHA-256:
`8a8c2502e889ebf741955492c9a9e1bdda1e69850292f740105340a6dffe4bfc`.
Native controls25, all survey models, previous releases and website remain unchanged.

## D.C. dated registration and separate native voting-mode reports

[Complete version-25 controls and factual inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-25/complete-analysis.zip)
retain five separate reports linked by the [official board](https://dcboe.org/):
**453,471 registrations as of September 30**, the early-vote-center
report's **27,118**, **72,903 Election Day in-person**, **53,736 drop-box
mail ballots received**, and **45,376 USPS mail ballots received**.
Different measures and cutoffs are **not added into all-mode cast ballots
or unique people**. Received mail is not independently qualified accepted/
cast ballots. Vote-center/drop-box location wards are not voter residence;
the dated register is not a matched election-report denominator.

The complete 13-page / 20-grid factual views preserve all 4,517 raw
slots, 1,515 count slots, 23 unknown counts and seven printed zero literals.
All eight wards / 144 native registration precincts are retained, not
relabelled as precinct voting results. Printed ward headers, not page
ordinals, identify registration geography. Merged detention-center cells
retain their day columns; drop-box ward blanks are not filled from a
printed daily total of zero, and USPS November 7-13 blanks remain unknown.
All 342 equations are evaluated: 326 complete reconcile, 16 remain incomplete.

**D.C. still has no Civic sample.** Registration does not create one:
no pooled-state projection, new conditional model, local/group allocation,
matched model residual, staying-home claim or fabricated interval.
The existing separate 185,086 ballot / 457,371 registration reference,
rate and all 51 prior state rows remain byte-identical. All 43 controls
and 31 scenarios survive; now 48 dispositions / 31 scenarios, not 31 states.
No new rate, map, all-mode count or website view.

Twelve tests, 31,661 independent checks and two exact blocked offline
reproductions pass. An unpublished page-ordinal draft was superseded
before publication. Immutable release `438945282` has twelve full
authenticated-draft/anonymous-published byte-verified assets. The
105,905,422-byte / nineteen-member ZIP includes both complete factual
reader views, native external parents/ward labels, typed scope, original
receipts/digests, complete version24 baseline, optional PDF extractor,
portable reader/shared code, tests, every query/result and checksums.
Full original contact prose, web bodies and compiled app code stay local.
SHA-256:
`8ee46200c534b07ccc570dd589908b5d011af67f8debb45f3cc36656ddebfb9a`.

[New stopped-route receipts](data/registration-access/20261109-04/observations.json)
record Michigan's statistics-index403 (427 bytes) and Tennessee's
election-index403 (919 bytes): no alternate client/cache/mirror or
web-parsed numerical substitutes. The current D.C. results response was
an app shell without new all-mode counts; it did not replace the earlier
qualified citywide reference. Earlier releases and access holds survive.

## Alabama monthly active and combined registration frames

November13 directory refresh: the original remains byte-identical at SHA256
`e0942c9ce7d5e390d9163fe16cbb654b5ede4161ac6ae980dae7e464825fc382`.
It is **already integrated below**, not a new control or model revision.
The shared direct-XLSX reader independently checks all15,400 cells,666 formulas
and2,513 blanks including headers; the2,293 blank count slots stay unknown.
No new source/model/website version is issued. Exact no-op record:
`data/participation-access/20261113-registration-source-noop-01/`.

[Complete version-24 controls and originals](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-24/complete-analysis.zip)
add the [official 2026 workbook](https://www.sos.alabama.gov/sites/default/files/election-data/2026-11/ALVR-2026.xlsx),
obtained from its explicit [registration-index link](https://www.sos.alabama.gov/node/3616).
Both originals returned200. The latest native sheet is **October**, not
the November URL directory: **3,390,357 active / 462,824 inactive /
3,853,181 combined registrations**. Exact cutoff day, clock and timezone
remain unknown. Active and combined frames overlap; never add them or
interpret inactive registration as ineligibility or nonparticipation.

All ten month sheets / 670 county-month rows / 15,400 grid slots /
14,280 count slots match independent XML and openpyxl views. All **2,293
blank counts remain unknown**. Native formulas and cached values are
preserved, never executed or recalculated. All 2,250 accounting equations
are evaluated: 911 complete equations reconcile; 1,339 remain incomplete.
Native race/federally-registered-any-race categories are not harmonized
or used as demographic participation groups.

Separate conditional **active 1,565,208.30 / 1,825,148.70** and
**combined 1,778,877.82 / 2,074,303.18** participant/nonparticipant source
units assume unvalidated statewide Civic transport. They are not observed
people, staying home, legal-eligibility certification or election-time
populations. No linked ballot/model residual, local/group allocation,
fabricated interval or new rate/map/website view.

Every prior state row, all 41 controls and 29 scenarios are byte-identical,
including Alabama's separate 3,852,947 election-reporting denominator,
1,693,621 count, rate and scenario. No substitution or repair.
Version24 has **51 state/D.C. rows, 43 dispositions and 31 scenarios**,
not 31 distinct states.

Ten tests, 164,529 independent checks and two exact blocked offline
reproductions pass. The standard-library mock/SSL harness import order
was fixed without changing source inputs, estimator, tests or blocking
probes. Immutable release `438922459` has ten full authenticated-draft/
anonymous-published byte-verified assets. Its 105,764,822-byte /
seventeen-member ZIP includes the entire original workbook, independent
grid, factual declaration/receipts, complete version23 baseline, portable
reader/shared code, tests, every query/result and checksums. SHA-256:
`5fe02b9da970fb3d1a5abc01a9751f3b8e9885a4e1b2d2d048284bc1da9a65cf`.
Earlier releases, access holds and accepted website remain unchanged.

## Same-type state source-model contrasts, not turnout-change estimates

[Complete comparison package](https://github.com/hanshanley/margin_of_error/releases/download/participation-ap-state-contrasts-20261109-01/complete-analysis.zip)
uses only the unchanged, already-public AP state-group inputs. It computes
2018-to-2022 **midterm** and 2020-to-2024 **presidential** source-model
share arithmetic: **505 distinct state/group/pair contrasts**, each
with separate poll-close/final views, including 413 non-overall contrasts.
All **6,426 comparison decisions** and holds are retained; two weight
views are not independent samples.

Both endpoints must already be public and supported, with identical
native variable/code/label. Full native group weights and unknown model
mass remain in the denominators. Exact rational voter/nonvoter/unknown
percentage-point differences reconcile to zero. No private source,
new fine cell or suppressed statistic is introduced.

These are **not observed turnout changes** or validated survey-model,
measurement or population comparisons. Repeated cross-sections do not
track the same people or fixed demographic memberships; final-weight
outcome calibration is not validation. Age/education/income labels do
not prove measurement equivalence; income bins are nominal source
categories, not independently qualified household income. Sex/gender
and race comparisons remain held rather than harmonized. The 2018
inference caveat, 2022 DE/WV and absent-RACETH5 holds, D.C. absence,
unknowns and all prior support/disclosure decisions remain explicit.
No causal/individual-retention/population-change claim or fabricated CI.

Ten tests, 183,662 independent checks and two exact blocked offline
reproductions pass. Native reductions and earlier qualified campaigns
were not rerun. Immutable release `438910558` has four full assets,
authenticated-draft and anonymous-published byte-verified. Its
1,221,147-byte / ten-member ZIP includes the complete prior public
package, all comparison queries/holds, unchanged source definitions,
new code/tests/results and checksums. SHA-256:
`314119ecc91494e52ba3c09c7db82ced4631830f292f97224bc9dae730f01498`.
Current state controls23 and the accepted website are unchanged.

**New distinct access holds:** the
[two-observation receipt ledger](data/registration-access/20261109-03/observations.json)
records Missouri's registration-index403 (4,550 denied bytes) and Ohio's
aggregate-portal403 (1,253,339 denied bytes). Both routes are stopped,
without another client/cache/mirror or promotion of cached counts.
Full denied bodies/app material stay local; no individual voter files
were downloaded. The automatic snapshot commit is preserved as parent;
unrelated dirty-root data are not overwritten.

## Minnesota registered-only snapshot and test-source exclusion

[Complete version-23 controls and inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-23/complete-analysis.zip)
add the [official current county table](https://www.sos.mn.gov/election-administration-campaigns/data-maps/voter-registration-counts/).
Its native caption says **November 2, 2026**: **3,927,036 Registered
Voters**, separately **94,621 Pre-Registered Voters**. The latter are
source-defined 16/17-year-olds and are **not added or age-projected into
the model denominator**. This date belongs to the current table, not
the older May/June workbook links or acquisition clock.

All 87 counties plus TOTAL / 267 cells / 176 count slots are retained.
Independent standard-library HTMLParser and lxml/libxml2 views agree;
both county sums reconcile to their distinct explicit parents.
Missing values are not zero, and county names are not inferred FIPS.
Exact time, timezone and active/inactive status remain unknown.
Registration is not independent legal-eligibility certification.

Conditional **2,937,408.57 participant / 989,627.43 nonparticipant
registered-only units** assume unvalidated statewide Civic transport,
not observed people or staying home. The earlier partial Minnesota
election observation is unchanged, not blended with the dated register.
All fifty other state rows, 40 prior controls and 28 scenarios survive;
version23 contains 41 dispositions and 29 scenarios, not 29 distinct states.

A distinct Montana election-results export page returned HTTP200 but
has a visible **TEST** header banner. It remains unqualified; no test
turnout/registration/candidate count is an administrative benchmark or
model input. Its test-status receipt is retained, not mislabelled403.
The earlier denied Montana registration-index route stays stopped.
Full test-page/session-form/app-code/contact material stays local.

Ten tests, 1,351 independent checks and two exact blocked offline
reproductions pass. Immutable release `438886468` has eight full assets,
authenticated-draft and anonymous-published byte-verified. Its
105,390,921-byte / fifteen-member ZIP includes the complete byte-exact
factual table, independent view, typed age/date facts, receipts/test hold,
entire version22 baseline, reader/extractor/shared code, tests and every
query. SHA-256:
`13a0fecb05d650f1013bf74c79fb630ac83b0dc1554ceed4a9d933aca0662ecd`.
No new website view, ballots/residual, rates/maps, population validation,
local/group allocation or fabricated intervals; earlier releases unchanged.

## Idaho month-labelled registration, separate from the ballot report

[Complete version-22 controls and inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-22/complete-analysis.zip)
add the [official November registration archive](https://voteidaho.gov/data-and-dashboards/voter-registration-totals/).
The acquired index explicitly selects 2026 / November and declares its
County, Legislative and Congressional CSV template; no filenames were
guessed. All three original CSVs were successfully acquired once.
Their identical native **Total is 1,056,803 registrations**.

The index's **November 2, 2026 update label is not an independently
qualified registration cutoff or live clock**. Status and timezone
remain unspecified. All 44 counties, 35 legislative districts, two
congressional districts and three state parents are retained. The views
are repeated margins, not three populations. All **609 raw cells /
504 count slots**, including headers and native cell spaces, match the
independent CSV reader; all 102 equations reconcile. No blank-to-zero
imputation, inferred FIPS or party-vote interpretation.

Conditional **756,202.53 participant / 300,600.47 nonparticipant
monthly-register units** assume unvalidated statewide Civic transport,
not observed people or staying home. Idaho's existing 731,980 separate
ballot-report count and Twin Falls registration disagreement
(41,878 versus 42,990) are unchanged. Its primary registered denominator
and rate stay null: the dated register is **not substituted beneath the
ballot count**. Only separate-scenario availability changes in the state
query; all fifty other rows, 39 earlier controls and 27 scenarios survive.
Version22 contains 40 dispositions and 28 scenarios, not 28 distinct states.

Ten tests, 3,051 independent checks and two exact blocked offline
reproductions pass. Immutable release `438865406` has eight full assets,
authenticated-draft and anonymous-published byte-verified. Its
105,305,071-byte / fifteen-member ZIP includes all three original CSVs,
full independent snapshot, factual declaration/receipts, entire version21
baseline, reader/extractor/shared code, tests and every query. SHA-256:
`b464688086fa16bbde73381932f414f459779efe4c3c509e8216515de226db03`.
Full index app code/contact details and personal records are excluded.
No new website view, local/group allocation, rate/map/population approval
or fabricated intervals; earlier releases and source holds remain intact.

## Oregon monthly registration and held returned-envelope context

November13 directory refresh: the original remains byte-identical at SHA256
`6ba27dc31ecb4b09d81ef9c9b3258dfa8fd44bdc8f2a1c34aa38d3dc5ab890b9`.
It is **already integrated below**, not a new source/scenario. Generic reviewed
PDF projections independently reproduce all2,146 count positions and preserve
the additional raw district-label blanks, native zeros and signed percentages.
All existing51 state rows/scenarios and full downloads remain unchanged.
Do not confuse a second cache/reader with new election evidence.

[Complete version-21 controls and originals](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-21/complete-analysis.zip)
add a distinct [monthly registration report](https://sos.oregon.gov/elections/Documents/Registration/2026-November.pdf)
already held locally. Its explicit county **Total is 3,112,307**,
corroborated by congressional, Senate and representative parents.
The native **November 3, 2026 preparation date is not a qualified
registration cutoff**; status and timezone remain unspecified.

All seven pages / 2,220 data slots preserve 2,146 count slots, 44 observed
zeros and 74 printed percentages. All 298 accounting equations reconcile.
The 36 counties, 49 congressional fragments/six subtotals, 30 Senate and
60 representative districts are repeated registration margins, not extra
populations. Native party affiliation and monthly stock changes are not
vote choice, participation or first-time registration.

Conditional **2,085,480.05 participant / 1,026,826.95 nonparticipant
monthly-register units** assume unvalidated statewide Civic transport.
The existing November 7 Oregon primary reference and **all 51 prior
state-query rows remain byte-identical**. Every earlier control/scenario
survives; version21 has 39 dispositions and 27 conditional scenarios.

The separate returned-envelope report explicitly warns against formal
analysis. Its 2,028,213 returned envelopes and October 16 active snapshot
3,117,439 are **held context only**, never new model/calibration inputs
or cast-ballot substitutes. Report generation on November 6 is not its
registration clock; timezone remains unknown. Legacy fine-cell
blank-to-zero transformations and county-day/party CSVs are not reused.
No new rates, maps, group/local allocations, population validation,
observed staying home or fabricated intervals.

Ten tests, 9,907 independent checks, a third original-PDF reader and two
exact blocked offline reproductions pass. Successful acquisitions and old
reductions were not repeated. Immutable release `438849204` has eight
full authenticated-draft/anonymous-published byte-verified assets.
Its 105,213,231-byte / fifteen-member ZIP includes both original PDFs,
new full independent views, declarations/receipts, version20 baseline,
maintained reader/extractor/shared code, tests and every query. SHA-256:
`f721fb06dc9e4f28e9d392065a4858ccfc316c0696419d1faa93393d09d7a9e6`.
Historical AP downloads and the accepted website are unchanged.

## Historical state-group VoteCast model shares

[Complete historical state-group package](https://github.com/hanshanley/margin_of_error/releases/download/participation-ap-state-demographics-20261109-01/complete-analysis.zip)
extends the already-verified AP/NORC 2018/2020/2022/2024 aggregate cache.
All **12,138 query decisions** cover 51 jurisdictions and both native
state-weight stages. The **3,206 non-overall group/weight views** describe
**1,603 distinct state/year/group cells**, each with poll-close and final
views of the **same sample**, not two independent estimates. Supported
group views occur in 45 / 44 / 40 / 46 states, respectively; all remaining
holds are retained. The complete package also retains 384 overall views
and the unchanged earlier 602-row national/state-overall package.

These are `LIKELYVOTER` source-weighted **model shares in a registered
survey frame**, not administratively observed group turnout, population
counts, staying home, a linked panel or a cross-study causal trend.
Final-weight outcome calibration is not independent outcome validation.
Native age, education, income, SEX/GENDER and RACETH5 labels are not
harmonized: the broader 2024 Asian/Pacific category remains distinct.
The 2018 state rows retain the publisher's 47-inference-state caveat
despite all fifty sampled. D.C. has no sample; 2022 DE/WV state inference
and the absent 2022 RACETH5 dimension remain held, not reconstructed.

Positive-weight support must reach 500. That is neither a precision nor
an anonymity guarantee, and the cache lacks per-model-class case counts:
no class-support threshold or design interval is claimed. Unknown/removed
groups remain in full denominators. Positive-cell complementary holds
apply within/across states, with synchronized poll-close/final masks;
all 2,114 relevant partitions are independently checked. No raw cases,
private held statistics, fine RACETH state cells or party-choice tables
are exported.

Four full assets in immutable release `438827134` are authenticated-draft
and anonymous-published byte-verified. Fourteen tests, **243,257 new
checks** and two exact blocked offline reproductions pass. The original
532,866-row / 132,196-check native verification was reused, not repeated.
The 1,044,743-byte / ten-member ZIP contains permitted selected inputs,
all held-query decisions, full prior AP package, verification provenance,
maintained selection/reader code, tests, results and checksums. SHA-256:
`22caef437af4e8126bd611a1d3ae0f98d3bc8920d81b7dd0e3e70487029e2372`.
Current state-control version20, earlier releases and the accepted website
remain unchanged. This adds research downloads, not a new deployed view.

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

## Further registration-source access observations

The [complete six-observation receipt ledger](data/registration-access/20261109-02/observations.json)
records five new HTTP403 holds: Iowa's separately declared November
registration PDF and preliminary participation release, Wisconsin's
statistics page, Massachusetts's distinct modern statistics hub and
Kentucky's registration index. The denied response bodies are held
locally; their actual byte lengths/hashes are recorded where exposed.
Wisconsin's web-tool body was unavailable, so its byte/hash fields are
null, not fabricated.

All five routes are stopped: no alternate client, cache, mirror or
guessed file. Web-parsed Iowa counts and discovery of a modern 2026
Massachusetts product are not native analysis inputs. Iowa's legacy
registration index separately returned404; its declared modern
Research and Data navigation led to the subsequently denied originals.
These are source-access holds, not zero populations or proof that
the data do not exist. Version20 numerical estimates and all complete
downloads remain unchanged. Continue distinct permitted or already-held
evidence rather than retrying these routes.

## Nebraska source-filtered registration count

[Complete version-20 controls and inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-20/complete-analysis.zip)
add the [official November registration-system report](https://sos.nebraska.gov/elections/voter-registration-statistics).
Its native **"Count of Voters Eligible to Vote" / Grand Total is
1,265,022**. This is a source-filtered administrative registry count,
**not estimated VEP**, active-only registration, independently certified
legal eligibility or observed participation. Filter criteria and
population transport remain unqualified.

Native **Processed: November 1, 2026, 2:00 AM** and **Printed:
November 2, 2026, 8:27 AM** remain distinct. Neither independently
establishes a registration cutoff or live update; timezone is unknown.
All seven pages / 93 counties plus state parent / eight count columns /
752 slots are preserved, including **126 blank slots**. Those blanks
remain unknown, not zero or complement recoveries. Coordinate mapping
prevents left-shifting counts across blank minor-party columns. Native
party affiliations are not votes; literal `Mcpherson` and raw header
glyph artifacts are retained rather than fuzzy-corrected.

Two independent coordinate readers agree. A separate original-PDF
ruled-cell-border extraction checks every slot without reusing the
maintained word grid. All 102 accounting checks are evaluated: 29
fully observed equations reconcile; 73 incomplete ones remain incomplete.
Conditional **778,723.61 participant / 486,298.39 nonparticipant registry
units** assume unvalidated statewide Civic transport, not observed
people or staying home. Native ballots/residual, rates, maps and
local/group allocation remain withheld.

Version20 contains 51 state/D.C. rows, 37 dispositions and 26 scenarios;
all fifty unaffected states, 36 prior controls and 25 prior scenarios
survive. Twelve tests, 5,018 independent checks and two exact blocked
offline reproductions pass. Immutable release `438806513` has eight
full authenticated-draft/anonymous-published byte-verified assets.
Its 104,086,275-byte / fifteen-member ZIP includes the original PDF,
complete coordinate/text views, receipts, version19 baseline, maintained
reader/extraction helper/shared code, tests and every query. SHA-256:
`c8b3b6664507bebea9e8d3fc7cecbe19f8182510d748f298961e787887b68893`.
No new website view or replacement of earlier releases.

**Distinct access follow-ups:** Montana's officially linked
`https://sosmt.gov/elections/regvotercounty/` returned **HTTP 403**:
8,237 denied-body bytes, SHA-256
`1f5da60ac7945d49f52c0441962910da414e65bac5ba375a872e065e7a62a837`.
The receipt is included; full denied bytes are locally held, not
redistributed. That route is stopped, without another client/cache/mirror
or a guessed embed URL. Nevada's registration-statistics web index
yielded only an unqualified iframe: no native numerical input acquired,
no actual HTTP 403 status claimed and no bypass attempted.

## South Carolina registration stocks and native demographic margins

[Complete version-19 controls and native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-19/complete-analysis.zip)
reuse the successfully acquired [official registration workbook](https://scvotes.gov/elections-statistics/voter-participation/).
Its explicit `RP0040 / Race: All / TOTAL / All Total` is **3,470,220
registrations**, not participating voters. **November 2, 2026 is the
declared report label**, not an embedded registration cutoff or clock.
Those fields/timezone and active/inactive status remain unknown.

All nine views, each with 46 native county rows and a state parent, are
preserved: overall plus eight source race categories, administrative
Female/Male/Unknown and four native age bins. The overall view and its
race views are not nine populations. County codes are not inferred FIPS.
Native race/Hispanic, gender and age categories are not automatically
CPS/Civic-equivalent; no crosswalk, group turnout or local probability
allocation is inferred. These group counts describe registration stocks.

All **14,121 cells / 6,768 registration slots**, including **945 missing
count cells**, retain their original distinctions. Numeric zeros remain
observed zeros; blanks are not zero or complement recoveries. All
2,588 accounting checks were independently evaluated. Fully observed
equations reconcile; incomplete equations remain incomplete.

Conditional 1,938,414.24 participant / 1,531,805.76 nonparticipant
**overall registration units** assume unvalidated Civic transport, not
observed staying home or validated group populations. Native ballots/
residual, population validation and new rate/map approval remain withheld.
Version19 retains 51 state/D.C. rows, 36 control dispositions and 25
conditional scenarios; all fifty unaffected states, 24 prior frames
and 35 prior controls survive.

Ten tests, 87,960 independent checks and two exact blocked offline
reproductions pass. The complete 103,538,706-byte / sixteen-member ZIP
includes the original 76,263-byte workbook, full frozen independent
snapshot/receipt/reduction-code provenance, version18 baseline,
maintained standard-library original-OOXML reader/shared helpers,
tests and every query. Successful acquisition and independent snapshot
were reused, not repeated. SHA-256:
`bb13c57bba29b96329af131ef490b5043cc376297a659027f84be5580a4598f9`.
Earlier releases/access holds and the accepted website remain unchanged.

## West Virginia preliminary agency participation reference

[Complete version-18 controls and permitted factual inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-18/complete-analysis.zip)
add the [official November 6 release](https://sos.wv.gov/article/wv-secretary-state-kris-warner-announces-canvassing-will-start-monday-november-9).
It reports preliminary statewide **463,912 ballots cast / 1,210,385
registered**, with native printed **38.33%**. The publication date is not
the count snapshot or registration cutoff; those clocks/timezone and
active/inactive status remain unknown. Canvass was pending at publication,
with further provisional/absentee review. No complete-count, all-55-reporting,
unique-voter or certification claim.

Early cast 162,349 and absentee **received** 7,001 remain distinct,
nonadditive facts; received is not relabelled cast. Four historical
percentages remain unmatched source context, without denominator/scope
qualification or trend fitting. The source-defined reference follows the
prior native-scope treatment: generic cast-ballot/rate fields remain null.

Conditional 476,060.13 participant / 734,324.87 nonparticipant
**same-release registered units** assume unvalidated Civic transport.
The native-minus-model contrast is -12,148.13, not population validation
or observed staying home. No fit to ballots, invented intervals, local/
group allocation or new map approval.
Version18 retains 51 state/D.C. rows, 35 control dispositions and 24
conditional scenarios; all fifty unaffected states, 23 prior frames and
34 prior controls survive.

Ten tests, 199 independent original-page/semantic/Fraction/package checks
and two exact blocked offline reproductions pass. The complete
103,190,172-byte / fourteen-member ZIP includes all nine relevant factual
numerical observations, twelve words of short factual fragments,
full-original byte provenance, version17 baseline, maintained extractor/
analysis/shared helpers, tests and every query. The full raw page is
retained locally, not redistributed: full article prose, compiled page
code, contact details and session headers are excluded. This remains
complete permitted numerical input data, not a metadata-only export.
SHA-256:
`c615e4533315fe9814d3c89eb6d50507552c8828fad261c86297a0f20a79ebb7`.
Earlier releases/access holds and the accepted website are unchanged.

## Kansas dated workbook registration frame

[Complete version-17 controls and native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-17/complete-analysis.zip)
add the actually declared October workbook from the
[official registration index](https://sos.ks.gov/elections/voter-registration-statistics.html).
Its native `By County / Grand Total` is **2,027,520**, with
**October 1, 2026** in every data row's `Date` column.
The date-only Excel style is not an observed midnight clock; time/timezone
and active/inactive status remain unknown. November/December index entries
were unlinked, so no later file was guessed.

All four worksheets are preserved: 105 counties, four U.S. House,
125 Kansas House and forty Kansas Senate districts, plus four repeated
Grand Total parents. These are repeated geographic margins, not four
populations or independent benchmarks; the state parent is counted once.
All 2,645 workbook cells and 1,946 party/total slots survive, including
299 missing/empty values. No Labels Kansas blanks and native United Kansas
empty strings remain unknown, not zero or complement recoveries. Matching
observed subtotals do not establish exhaustive party partitions. Affiliation
is registration accounting, not voting behavior.

Conditional 1,140,329.95 participant / 887,190.05 nonparticipant
**dated-registration units** assume unvalidated Civic exchangeability,
not observed staying home or group/local populations. Native ballots/
residual, population validation and new rate/map approval remain withheld.
Version17 retains 51 state/D.C. rows, 34 control dispositions and 23
conditional scenarios; all fifty unaffected states, 22 prior frames and
33 controls remain unchanged.

Ten tests, 24,725 independent checks and two exact blocked offline
reproductions pass. The standard-library numerical reader decodes the
original workbook itself and compares every cell with an independent
openpyxl view. Raw types/styles/shared formula text, attributes and cached
labels remain preserved without formula execution.
The complete 103,117,422-byte / seventeen-member ZIP includes the original
46,886-byte workbook, independent snapshot/receipt, version16 baseline,
maintained code, optional refresh, shared helpers, tests and every query.
SHA-256:
`0df62bcce6d586ffff6e3fcc052a6b4634ddcb6e25ec63b9374ec33d599956ef`.
Earlier releases, source/access holds and accepted website remain unchanged.

## Oklahoma and Pennsylvania source-registration frames

[Complete version-16 controls and native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-16/complete-analysis.zip)
add two distinct official registration reports, not ballot counts.
[Oklahoma's index](https://oklahoma.gov/elections/voter-registration/voter-registration-statistics.html)
declares November 1, 2026; its native `Grand Total` is **2,455,735** and
the PDF prints **11/1/2026 3:05 AM**, timezone absent. The printed report
clock is not a live update or independently matched survey cutoff.
[Pennsylvania's archived general-election report](https://www.pa.gov/agencies/dos/resources/voting-and-elections-resources/voting-and-election-statistics)
has native `Total / All Parties` **9,052,695**. **November 3, 2026 General
Election is an election label, not a registration cutoff.** The latter
remains unknown; no report time or timezone is invented.

All 77 Oklahoma / 67 Pennsylvania counties, both native state parents,
source labels/codes and 730 count cells are preserved. Native county codes
are not inferred FIPS. Party affiliation is registration accounting, not
votes; active/inactive status is unspecified. Notes about a separate
weekly party-change product do not qualify Pennsylvania's archive report.

Conditional participant / nonparticipant source-registration units are
1,176,234.68 / 1,279,500.32 for Oklahoma and
5,270,583.03 / 3,782,111.97 for Pennsylvania. These assume unvalidated
Civic exchangeability, not observed staying home or independently established
populations. Native ballots/residual, group/local allocation and new
rate/map approval remain withheld.

Version16 retains 51 state/D.C. rows, 33 control dispositions and 22
conditional scenarios. Ten tests, 3,021 independent checks, a third PDF
extractor and two exact blocked offline reproductions pass. All 730 cells,
native row equations and county-to-state column sums reconcile. All 49
unaffected state rows, twenty prior frames and 31 controls are preserved.

The complete 102,937,191-byte / fifteen-member ZIP includes both original
PDFs, full independent frozen extractions, receipts, version15 baseline,
maintained readers/optional refresh/shared helpers, tests and every query.
SHA-256:
`d4d0d4ca4baf0c326ef84e0c98ffd7f122d83870eabf037ea5271e0642e17cc7`.
Earlier releases, access holds and accepted website remain unchanged.

## New Jersey dated total-registration frame

[Complete version-15 controls and native inputs](https://github.com/hanshanley/margin_of_error/releases/download/participation-state-controls-20261108-15/complete-analysis.zip)
add the [official General Election Day county registration report](https://www.nj.gov/state/elections/election-information-svrs.shtml).
The native statewide `total` is **6,747,375**, dated **November 3, 2026**.
Active/inactive status and time-of-day/timezone are unspecified. An
election-day report date does not independently validate the survey/cohort
transport or an eligible population. All 21 counties, ten native party-code
columns and total remain intact. Affiliation is registration accounting,
not party voting; source codes are not reinterpreted.

Conditional 3,153,315.91 participant / 3,594,059.09 nonparticipant
**dated-registration units** assume unvalidated Civic exchangeability.
No observed staying-home claim, statewide ballot reference, residual,
group/local allocation or new rate/map approval. All fifty unaffected
state rows, nineteen prior frames and thirty controls are preserved:
version15 has 51 state/D.C. rows, 31 dispositions and twenty scenarios.

Ten tests, 507 independent checks, a third PDF extractor and two exact
blocked offline reproductions pass. All 242 count cells, source row
equations and county-to-state sums reconcile. Only extraction-layout
whitespace is normalized in label comparison, not substantive aliases
or counts; both full original extractions remain available.

The complete 102,493,352-byte / sixteen-member ZIP includes the original
48,054-byte PDF, both frozen extractions, receipts, version14 baseline,
maintained code, optional PDF refresh, shared helpers, tests and all queries.
SHA-256:
`182f8b721da13b98207de1b0f408104a77ee70f16c594ccd53aa4506c22eb132`.
New York and Maryland's distinct declared originals returned 403; both
routes are stopped and no cached counts are promoted. Prior downloads
and the accepted website remain unchanged.

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
remains open under the existing single 45-minute continuation.

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

**New York/Maryland registration originals, November 9, 2026 UTC:**
[actual receipts](data/new-jersey-register/20261109-01/access-holds.json)
record 403 for New York's declared November 1 county workbook and Maryland's
declared October PDF. New York's body was not captured; no bytes/hash are
invented. Maryland's captured 17-byte error body has SHA-256
`2938e9f1284180959e33ab1718d0793a72ff6e4cdb8108c34dcd14e69446de5c`.
Both routes are stopped, without another client/cache/mirror or using
web-parser/search-snippet counts as acquired native data. The separate
successful New Jersey report above does not resolve these holds.

**Distinct registration follow-ups, November 9, 2026 UTC:**
[four recorded access/link observations](data/source-access/20261109-01/register-followups.json)
hold Texas's advertised November registration page and both Maine
active/inactive workbooks after HTTP403. All three routes are stopped:
no other client, cache or mirror, and no search-snippet count promotion.
Louisiana's official statewide link contains an unresolved `--environment--`
hostname and returned 502; no production hostname was guessed.
Maine's index labels its files March 7, not November; the separate layout
example is not workbook/date qualification. Original response bodies were
not captured by the web tool, so no body sizes/hashes are invented.
No new frame, observed turnout or change to complete version14 downloads.

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
