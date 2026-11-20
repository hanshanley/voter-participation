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

Validation and collection run in separate dependent jobs, each with the existing
30-minute execution limit. Full source/analysis regressions must pass before any
collection or publication starts. Both jobs check out the workflow's exact commit,
not a newer `main` that the tests did not inspect. Starting February 1, 2027 UTC,
the Monday 10:19 UTC sweep checks only the reviewed late archives. It includes
the UF Election Lab statewide VAP/VEP series for all 50 states and D.C. plus
the separate U.S. aggregate, the six existing state-level products, Minnesota's
paired statistical TXT and statewide reporting table, Bath, Buxton and every town in the shared
VotingWorks registry. Hourly and weekly collection and scoped export attribution
use the same municipal registrations. Newly reviewed VotingWorks registrations
do not require a workflow change. The sweep runs `refresh-selected --late-archives`;
it does not recollect congressional races or any other unselected feed. Manual dispatch
retains its explicit override.

The weekly UF check follows the same advertised edition, schema and license
guards as hourly intake. An inaccessible or incompatible UF edition leaves
its last-good values and source edition intact and marks them retained; it
does not block a compatible revision in another archive. An explicit
UF-only `--sources` request still fails closed if acquisition fails.

North Carolina's 2026 voter-history and registration statistics are paired
only when both official indexes advertise the exact general-election archives.
The hourly and late-archive paths share this adapter. It checks the complete
county inventory and publishes only the four statewide age aggregates, with
separate original-file pins and report editions, in the complete analysis ZIP.
The source-defined fractions use active and inactive registration, not VEP
or ballots cast. Listing, statewide county inventory and a computed fraction
do not establish certification or completion. No source fine cells are exported.

Indiana's Election Division archive supplies its own statewide and 92-county
`Voters Voting` and `Registered Voters` series. The same hourly and weekly
adapter checks the exact 2022, 2024 and 2026 general-election links, not the
live contest feed or primary reports. The complete analysis download carries
the report's columns, edition and original-file pin, and keeps any raw count
disagreement visible. The 2022 statewide mode sum is 5,464 higher than the
printed `Voters Voting` total; the state and four affected county fractions
are withheld. The 2024 columns reconcile. Only a reconciled November 2026
report can affect the statewide map: all 92 county rows, the printed state
totals and both mode columns must agree. The map uses the source label
`Voters Voting`, not ballots cast. Historical rows and county-level archive
figures remain separate from the current map.

California (1990–1994 and 1998–2024 biennial general elections), Kansas (2022) and New Jersey
(2020 and 2022–2025) county turnout archives are
checked by the same hourly collector and weekly sweep, using the exact
general-election reports linked by their official indexes. The complete
`release/participation-state-county-turnout-archives.csv.gz` query retains all
printed county and state totals, available report editions and report hashes.
An index acquisition failure is shared across its archive feeds for that run.
Each feed records its own failure and retains its last verified report, if any.
The next run can retry a transient outage; durable access stops still apply.
Kansas's 2022 Stevens County and statewide registration fractions are withheld:
the workbook prints 7,979 ballots against 3,246 registered for Stevens and
includes that count in the state total. New Jersey's 2023 and 2025 elections are
identified as off-year, and the 2020 and 2022 amendments retain their edition dates
and affected counties. These are historical source snapshots, not 2026 observations,
eligible-population rates, or comparisons that assume stable county boundaries.
California's reports must reconcile all 58 counties and statewide totals before
acceptance. The export keeps the published `Total Voters` or `Ballots Cast`
measure, the separate eligible-to-register series, and any printed registration
fraction disagreement. The 2022 and 2024 registration bases exclude registrations
after the 15-day report. The 1990, 1992 and 1994 scans use checked transcriptions
of exact PDF bytes. Changed scans retain the last accepted edition until reviewed.
The 1992 population column is voting-age population, not eligible to register.
The 1994 county report and later statewide series disagree on Total Voters;
the archive preserves the county report figure and documents the discrepancy.
The 1996 scan still needs transcription checks. The hourly collector and weekly
sweep also check for the November 3, 2026 report on the official index. A matching
general-election link and a reconciled report are required for a separate
`release/participation-ca-2026-county-turnout-report.csv.gz` export. Rates are
withheld if the registration timing is not verified. The export does not replace
the current native turnout feed or claim certification.

The historical survey release also replays the eighteen original Census CPS
Table 4b/4c workbooks for 2008–2024, plus the 2008 Table 4a control. The separate
`release/participation-cps-published-state-tables.csv.gz` keeps the Census
survey estimates and their published 90% margins of error for voting-age and
citizen voting-age populations. Counts are rounded source estimates in
thousands; `B` and `-` remain source markers rather than reconstructed rates.
Both workbook totals and the original group labels are preserved. The race and
Hispanic-origin groups are not exclusive. This is not a new respondent model,
an administrative vote count, or a method for allocating state rates locally.
Legacy `(B)` suppression is retained. The 2010 age bands include 25–44,
65–74, and 75+, which are not split or merged into the later bands. The 2008
Table 4b totals agree exactly with 4a. Each 4c age frame must match its 4a
total, preserve native age bands, and reconcile its rounded counts and rates.
Florida, Georgia, and Hawaii age frames fail and are held; their Table 4b
overall, sex, race and Hispanic-origin rows are not withheld on that basis.
One impossible South Dakota registration percentage and any margins printed
without a usable estimate are withheld and flagged; the unmodified originals
are included. No replacement estimates are computed.

The same package includes the original A-3a/b and A-5a/b workbooks. A
separate `release/participation-cps-state-overall-history.csv.gz` provides
published overall state voting and registration rates, 1972–2024. The
workbooks do not publish margins of error or a U.S. benchmark; rates not
available keep `N` or `not_in_table` instead of a zero. Citizen voting-age
rates before 1996 use a different citizenship measurement regime and are
flagged as not directly comparable. This series does not override the
election-edition estimates, administrative counts, or demographic rates.

The North Carolina State Board of Elections' two statewide general-election
tables are checked in the regular and late-archive sweeps and the explicit
`NC-general-election-turnout-history` scope. The historical CSV preserves
`Ballots Cast` and the source's `Eligible Voters`, not Census CVAP or a
generic registration estimate. The source query keeps both tables' original
numeric literals. Primary rows are excluded, missing years are never zero,
and mismatched printed rates are withheld without replacing the counts.
This series does not overwrite the current canonical statewide observation.

West Virginia's 2008-2016 general-election county reports use the same
county-archive sweep. Each PDF must match the declared election, all 55
counties, and the separately printed statewide counts. The 2008 and 2010
reports explicitly derive their numerator from voter history, so their
counts are exported as `reported_voter_history_credits`. The other three
editions keep the source's `Ballots Cast` label. Rates use the registration
denominator printed in the same report. The resulting query is separate
from EAC and does not change modern count shards or certify any 2026 result.

The hourly cron, selected-source mode, durable access stops, last-good retention
and complete-query artifacts are retained. This separation prevents
the regression suite from consuming the collection/publication/cache-save budget.
The website's existing hourly data-only consumer remains separate; no Pages build
or respondent refit is required to consume a compatible new source snapshot.

### Unattended handoff and recovery

The collector checkpoints its complete packet before publication. A later
run first resumes any staged publication. If the preceding full collection
or weekly archive sweep stopped after its checkpoint but before publication,
the next run in the same lane can reuse the complete artifact only against
the original data ref. Weekly recovery also requires the packet to cover
exactly the current weekly registry; if the registry has changed, it checks
the current sources instead. Hourly runs (including skipped runs after the
cutoff) do not occupy the weekly recovery slot. Ad hoc scoped collections and
explicit replays are not automatic checkpoint candidates. An explicit failed
publication step is not an automatic replay trigger. The public source pointer
and accepted collector state advance together; newly encountered access stops
survive staging.

The website resolves the accepted source commit once per cycle. A matching source
and engine skip bulk download, compilation and publication. A fresh runner can
verify and activate a staged runtime for the same source and engine; a stale or
changed staging receipt cannot overwrite newer accepted data. Publication keeps
the complete analysis ZIP, the rolling model seed, and exact predecessor bindings.
If the publisher stops before either a source checkpoint or a runtime stage is
durable, the unfinished work may need to run again.

The separate website health workflow checks scheduled successes and source-to-site
lag. It opens or updates one issue for repeated failures, a missed three-hour
success window, a runtime/catalog mismatch, or a revision not active after two
hours. A newer source revision does not reset the handoff timer. Verified catch-up closes
the issue. After the hourly cutoff, the monitor checks the Monday archive slot
after a three-hour grace period and still checks publication handoff and
catalog consistency. Skipped hourly collection jobs do not satisfy the weekly
check; a successful scheduled run or archive-only fallback does.
Source-native result clocks and expected analytical holds do not by
themselves trigger an alert. The monitor runs in GitHub; it cannot alert during a
GitHub-wide outage.

```sh
# Collect into a fresh work directory using the reviewed registry.
python -m scripts.results_intake collect --registry data/results-intake/registry.json --work-dir "$WORK"
# Resume a staged source packet without reopening any election source.
python -m scripts.results_intake resume-publication
# Merge saved denials while the collector is idle, against a reviewed exact data head.
# This does not open election sources or replace the accepted numerical snapshot.
python -m scripts.results_intake merge-source-stops --expected-head "$RESULTS_DATA_HEAD" "$SAVED_LEDGER_1" "$SAVED_LEDGER_2"
# Prepare the analytical refresh without changing active publication.
python -m scripts.automatic_runtime --repository "$WEBSITE_CHECKOUT" --work-dir "$RUNTIME_WORK" --results-pointer "$PINNED_POINTER_URL" --no-publish
# Inspect production handoff health without issuing writes.
python -m scripts.automatic_health
# In the extracted complete results / analysis ZIP, respectively:
python3 code/reproduce.py replay --package . --output reproduced
python3 code/reproduce.py --replay-package . --output reproduced
```

## Congressional revision guards

### Iowa versioned returns and county ballot counts

The hourly collector reads Iowa's published Clarity version pointer and
reconciles the federal JSON returns and the same edition's statistical text
report. House and Senate candidate rows remain separate from the administrative
ballot counts. Blank party labels remain unknown; named and generic write-ins
are not merged. The separate Iowa evidence does not replace the national
provider or qualify a conditional model.

The runtime selects the all-method ballot frame only when all 99 county
counts reconcile to the statewide control and match the pinned 2026 county
reference. Early-vote and mail-return records and the earlier Linn and Marion
observations remain in the complete download. Counts and publication metadata
retain their original edition on failure; source registrations and printed
percentages are context only. Reporting completeness is not certification, and
the website publication timestamp is not a ballot-update timestamp.

### Utah statewide JSON candidate evidence

`UT-official-house-candidates` independently captures the already-declared
Utah statewide general-election JSON product. The common collector acquires
that root once per run; the existing four-county PDF adapter reuses its verified
body without changing its county queries or requiring PDF success for federal
candidate evidence. Source-stop checks precede even a warmed-body lookup.

All four House contests and 20 retained candidate rows remain inspectable,
including literal native names, party names and null abbreviations, named
write-in flags, stable identifiers, vote counts and original UTC clocks.
The adapter checks election/production/office identity, complete district
inventory, candidate sums, integer safety and prior identity/finality.
Clock comparisons retain all seven native fractional digits. Upward, downward
and true-zero corrections are supported; failures, missing candidates and
clock rollback retain the last-good observation and its own clocks.
An identical capture remains a no-op. A selected refresh can use this source
ID without recollecting the national feed or the separate county PDFs.

The official named write-in does not explain the national provider's distinct
generic write-in row. Both remain separate evidence; no count is erased,
allocated or added across providers. Exhaustive write-in coverage, provider
equivalence, conditional-model eligibility and participation qualification
remain false. Native reporting fragments are not certified precinct counts.
The full official exports and complete reproducible source/analytical packets
retain the candidate facts, holds, adapter, tests and factual fixture.

### Virginia's derived complete federal frame

The existing Virginia statewide/locality collector already retrieves the state
document and all 133 declared locality documents. `results_native_congress.py`
derives the complete 11-district House frame from that same query, without a
second collector or duplicate requests. A selected refresh of
`VA-registered-1657a8451bae522c` also refreshes this dependent federal evidence;
an unrelated selected source leaves it unchanged.

The derivation checks all 47 candidates, 11 generic write-in rows, 145 locality
contest fragments, five voting methods and every candidate/method/component
sum. Native candidate identifiers, literal parties, locality-election UUIDs,
method labels/group UUIDs and the full source-receipt manifest remain bound.
Missing or contradictory data, changed identities, primary/test products,
future clocks and any locality-clock rollback retain last-good evidence.
Candidate votes remain candidate votes, never a participation numerator.

`native_official_house.py` separately reproduces an explicit full-frame
analytical review from retained official facts, the historical scientific
comparison and retained FEC candidate/authorized-committee evidence. Every
retained candidate maps one-to-one, including all minors and generic write-ins.
Literal formal-name formatting and documented initials/suffixes may support
identity; guessed nicknames, conflicting suffixes and ambiguous matches refuse.
FEC supports identity only, not ballot presence, vote counts or completeness.

A compatible native revision conditions all nine existing Virginia model
variants on the complete official D/R/O vector, without refitting respondents.
It never mixes provider and official counts, allocates aggregate Other, erases
provider discrepancies or grants new scientific/historical eligibility.
The independent native last-good checkpoint preserves numerical outputs and
their own clocks after failure, rather than falling back to an incompatible
national-provider frame. Complete source and analytical packets retain all
queries, review/crosswalk, code, tests, inputs and numerical outputs.

Whole-frame precedence explicitly disables changes to the separate national
candidate seed for RI and VA. That restriction does not apply to the existing
protected Hawaii path, whose exact same-inventory official candidate/control
seed must continue advancing. Having source-revision metadata alone is not a
reason to suppress that previously supported update.

### Oregon statewide printed candidate evidence

The existing hourly collector includes the Oregon Secretary of State's single
statewide federal-results product, reached from its declared export page.
`OR-official-house-candidates` preserves all six House contests, literal candidate
and fusion-party labels, named minor candidates, generic write-in rows, printed
totals, native reporting counters and its independently dated PT source clock.
Select that source ID to refresh it without recollecting the national feed.

The parser checks each candidate/total's native contest identity, the complete
six-district inventory, exact integer totals and reviewed party roles. Subsequent
captures reject regressing/future clocks, lost candidate identities, changed
contest IDs or source-unit inventories. Upward, downward and true-zero corrections
are accepted; a failure retains the complete prior observation and its own clock.
An identical capture remains a no-op. No provider counts are added together.

The native notice says "Write-in results are not reported on this site." Printed
generic write-in rows are retained, but this unresolved scope statement prevents
claiming an exhaustive counted write-in universe. Zero reported precinct counters
remain literal even beside positive candidate counts. This scheduled partial
evidence **does not qualify an Oregon model**, participation numerator, synchronized
provider comparison or certified result. Existing analytical holds stay in force.
Both full official exports and source/analytical complete downloads retain the
selected facts, scope notice, code, tests, and all candidate/category discrepancies.

### Separately reviewed split-block boundary evidence

The raw `electoral-recorded-districts.csv.gz` download retains its recorded
endpoints. Its `map_*` columns link each district to the separate map comparison,
with that comparison's actual source clock, boundary method and holds.
`map_qualified_margin_change_pp` and the `map_previous_*` and `map_current_*`
major-party counts come from the linked comparison, not from the raw endpoints.
The race ID identifies the baseline query in `congressional/results.json.gz`;
the source URL and checksum identify the current observation, and the boundary
review version identifies the geography decision where available. Held
comparisons have no qualified swing value. Only an unambiguous,
advertised voting-seat race with the reviewed historical district is linked;
retained, non-advertised alternatives remain in the full congressional queries.

The immutable national 119th/120th Congress BEF review is retained unchanged.
`data/results-intake/district-splits/20261118-01/` adds a separately pinned review
for Colorado block `080010096072000`, affecting CO-07 and CO-08 in 2024-to-2026
comparisons. It contains both complete original congressional geometry ZIPs,
the complete 2020 Census block polygon response, layer metadata and acquisition
receipts. This is new split-geometry evidence, not new election returns.

The compiler requires equal complete BEF memberships, the same full split-block
declaration, all eight Colorado districts, valid unsimplified NAD83 district
polygons and the exact full-resolution block query. Both original district
partitions must cover the block with nonoverlapping interiors; each positive-area
fragment must be exactly geometrically equal across congresses. There is no
coordinate tolerance, geometry repair, simplification, population weighting or
allocation of historical votes. Coverage is tested on original polygons before
clipping, avoiding floating-point artifacts from dissolving separately clipped
pieces. A changed fragment, additional unresolved split, wrong cycle, missing
original or changed review refuses qualification.

The rule removes only these two boundary holds. Candidate, party, stage, round,
missing-count and freshness guards still apply on every automatic refresh.
No House-state behavioral model is qualified by this geographic evidence.
These source-product comparisons are not certification of legal boundaries.

Reproduce the geometry review from the repository with its existing geographic
dependencies, without acquiring anything:

```sh
python3 -m scripts.congressional_split_blocks \
  --repository . --output /tmp/reproduced-split-review.json
cmp /tmp/reproduced-split-review.json \
  data/results-intake/district-splits/20261118-01/review.json
```

The analytical complete download includes every original above and its compiler.
Within an extracted analytical packet, the equivalent command is:

```sh
PYTHONPATH=code python3 -m scripts.congressional_split_blocks \
  --repository inputs/reviewed-congressional-sources \
  --output reproduced-split-review.json
cmp reproduced-split-review.json \
  inputs/reviewed-congressional-sources/data/results-intake/district-splits/20261118-01/review.json
```

Recorded-results intake accepts newly advertised candidates or aggregate Other
categories only with a newer native count version and every previously known
candidate identity retained. Removed candidates, changed names/parties, lost
known counts and regressing clocks still retain last-good results. Original and
successor candidate inventories remain in their complete versioned queries.
This intake rule does not approve an analytical frame: the model bridge retains
its exact reviewed candidate-inventory requirement.

The five-minute future-clock tolerance is measured against collection-start UTC
plus elapsed monotonic time, not the stale start clock after earlier source
families have completed. Retrieval/validation time never replaces a native
count-update timestamp. Unchanged accepted observations remain exact no-ops.

## Current state-by-guard downloads

Each analytical runtime generates a versioned state-by-guard matrix from its
actual decisions, rather than reusing a hand-maintained coverage snapshot.
`congressional/results.json.gz` contains it under
`analytical_handoff.state_guard_matrix`; the complete
`congressional/queries.json.gz` retains the same matrix alongside every exact
state/race decision. The existing `congress-analytical-decisions.csv` adds
`overlapping_guard_families` and `missing_evidence` columns.

Classification examines the reason after a race identifier: `not_ranked` in
that identifier is not evidence of an unresolved election-stage restriction.
Actual ranked-choice/stage restrictions remain. Identity, Other/write-in,
party coverage, source universe, geography, denominator, freshness and original
scientific restrictions are separate, overlapping diagnostics. Unknown future
reasons remain exact and explicitly unclassified, not silently approved.

This diagnostic never changes qualification, source counts, model points or
original hold strings. Outage, recovery and newly compatible observations
change its current classification through the existing hourly runtime. Frozen
models retain their last-good counts and source clocks; evidence requirements
describe the observed hold, not a claim that the missing source does not exist.
All existing full downloads and historical matrix versions remain available.

## Reviewed official category reconciliation

### Whole-official-frame analytical precedence

The hourly runtime defaults to the deployed whole-block boundary-reader contract.
The exact Colorado split-fragment proof remains preserved and reproducible, but
its two additional comparisons require the compatible reader to be delivered
before enabling `--accept-reviewed-house-split-geometry`. This is a delivery
dependency, not a withdrawal of the geographic finding. Numerical packages
preserve the effective boundary policy and replay it explicitly; the complete
successor package also retains the separately reproducible split evidence.

`official_house_precedence.py` supplies a separately reviewed successor for
Rhode Island, not a waiver of the original provider-category checks. Its
`data/results-intake/official-house-precedence/review.json` is reproduced from
the complete retained official candidate query and previously reviewed
candidate/category equivalence. Scientific eligibility, historical endpoints,
both districts, every named minor candidate and generic write-in remain pinned.

Subsequent hourly observations can condition all nine existing model variants
on the **entire** compatible official D/R/O vector. National-provider counts
are neither added to it nor substituted for individual official categories.
The national feed remains the raw broad intake; full official queries,
provider frames, signed disagreements and provider-path holds stay downloadable.
This matters when a newer official write-in/minor revision differs from a stale
provider aggregate: the original equality guard still refuses that provider
path, while a separately qualified complete official endpoint can advance.

The official source must report the complete reviewed election, stage,
district, candidate and voting-mode inventory. Its native count clock cannot
regress against its rolling last-good observation or exceed its own acquisition
receipt. Count decreases and actual zeroes are legitimate corrections; missing
or changed identities, incomplete reporting, outages and incompatible clocks
retain the last-good numerical results and their dates. Failure does **not**
fall back to the discrepant national frame. An unchanged input remains a no-op.
The official checkpoint remains separate from the national candidate seed;
advancing one never rewrites the other provider's candidate identities or counts.
No new respondent fit, scientific comparison, turnout numerator or denominator
is introduced. Other states still require their own compatible evidence.

The existing complete analytical archive includes the new policy, original
category evidence, code/tests, full nine-variant outputs and rolling checkpoint.
Its literal replay command below revalidates the policy against that evidence
before reproducing the outputs; no further source acquisition is required.

### Automatically retained official candidate frames

The reviewed `data/results-intake/official-congress.json` declaration registers
Nebraska's complete statewide `resultsSW.aspx` House tables as a separate
candidate-evidence family. Ordinary hourly collection refreshes it once per
source body; selected refresh can acquire only this product:

```sh
python -m scripts.results_intake refresh-selected \
  --registry data/results-intake/registry.json --work-dir /tmp/election-intake \
  --sources NE-official-house-candidates
```

The selected command requires the existing accepted collector state in that work
directory, as does any selected refresh. It retains all other acquisitions.
The workflow equivalent is:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation \
  --ref main -f refresh_sources=NE-official-house-candidates
```

All three districts, literal names/parties, source identifiers, printed totals
and reporting counters are retained. Partial reporting is explicit, never
certification. A missing native update clock remains null. Upward and downward
count corrections and explicit zeroes are accepted only after source identity,
complete table inventory and printed-total checks; missing/invalid counts or
changed layouts retain the last-good frame and its own provenance.

The complete source download adds `congress-official-candidates.csv`; the
analytical download includes it under `congressional/`, together with full
official candidate queries and signed named-minor-versus-provider-Other
differences. The runtime JSON exposes `official_candidate_evidence` and
`official_candidate_reconciliation`. Provider counts are never added to or
silently replaced by these counts. No absent generic write-in row is treated as
an observed zero. Equal subtotals alone never prove universe equivalence.

This evidence is excluded from participation observations and never supplies
ballots, unique voters, a denominator, new swing qualification or a conditional
model endpoint. The unresolved counted write-in universe, source precedence
and candidate-to-model bridge remain separate evidence requirements. Reproduction
uses the existing literal commands from each complete archive:

```sh
python3 code/reproduce.py replay --package . --output reproduced
# In the separate complete analytical archive:
python3 code/reproduce.py --replay-package . --output reproduced
```

`congressional_category_reconciliation.py` validates a complete official
candidate inventory before approving a source-category bridge. Its reviewed
Minnesota statewide semicolon family requires all eight districts, every named
candidate and a distinct generic write-in row, exact election/stage identities,
native control equations and the original evidence pins. Named minor candidates
are never folded into generic write-ins. Native candidate identifiers retain
leading zeroes; absent capture/update clocks stay unknown.

The approved successor removes only the reconciled category guard. Independent
identity, scientific, source-universe, geography and election-stage guards remain.
Future observations use the ordinary stable provider/candidate identity and
native-clock checks automatically, including downward revisions and explicit
zeroes. No assistant approval is required for each refresh. Inventory or identity
changes fail closed and retain the last compatible model result with its own
source dates. This approval does not establish current counting completion,
certification, ballots, unique participants or a turnout denominator.

The complete runtime package includes the original official file, independent
verification, predecessor review, full category decisions and all nine numerical
outputs. Providers' named-count discrepancies remain inspectable; the broad
national feed supplies the selected current endpoint and is not added to the
official inventory's totals.

## Official at-large candidate name declarations

The official-report successor to `congressional_candidate_identity.py` accepts
an explicitly declared name/quoted alias from the same native candidate row in
an official `.gov` general-election report. Approval requires the exact source
state, election date and stage, at-large House office, and a unique full-name
anchor in the complete retained FEC evidence. The older campaign/party
declaration contract is unchanged. This is not a nickname dictionary or
initial-only match, and a local report does not supply statewide endpoints.

The successor retains the complete category, primary-declaration and FEC
predecessors and all old candidates. It removes only resolved identity guards;
independent scientific, write-in, source-universe, stage and geography holds
survive. Stable provider IDs and advancing native clocks then permit compatible
hourly corrections, including decreases. A changed inventory or incompatible
frame keeps the last compatible conditional model with its own dates.

The complete archive includes every selected identity fact, original source
byte pin, independent extraction receipt, decision, test, predecessor and
numerical query. The original official PDF stays private; offline reproduction
revalidates selected factual declarations rather than re-extracting excluded
publisher material. Neither FEC registration nor name equivalence independently
qualifies complete ballot coverage, unique participants or a turnout denominator.

## Separate statewide turnout intake

California's existing native `status_GG.json` family refreshes its separately
declared Statewide parent as well as all 58 counties. Complete native county
counts and registrations must reconcile to that parent, which is excluded from
the county sums. The statewide observation keeps its source-defined
`voterTurnout` measure and existing native-registration denominator qualification;
neither reporting completeness nor literal SF/F status establishes certification.
The source-printed percentage and three native report timestamps remain distinct
from the calculated registered-frame fraction. Existing percentage mirrors are
updated together; held denominator qualifications remain held.

The runtime migrates the exact hash-pinned legacy California statewide display
to its existing canonical observation once, then follows the normal exact-view
successor binding. Other stale or edited display records are not rebound.
Source failures retain last-good counts, fractions and clocks. This is newly
automated integration of an existing source and observation, not new geographic
coverage or an eligible-population/group turnout estimate. It needs the updated
runtime engine pin, not a Pages deployment.

Nebraska's already scheduled `VoterTurnoutDetails.aspx?map=PREC` source also
refreshes its directly printed statewide header. The canonical statewide
observation is deliberately separate from the selected county/unit inventories.
Its exact source, measure, election and observation identity are required;
matching desktop/mobile turnout gauges and complete reporting counters are
checked. A statewide value below any individual reported unit is inconsistent
and refused, but unit counts are never summed to manufacture the statewide
parent or county parents.

The same captured query binds the canonical record and the existing global
statewide mirror. A one-time exact legacy preimage permits migration; subsequent
updates require the prior canonical binding, so independently edited mirrors
fail closed. Printed percentages stay separate from calculated native-registration
fractions. A changed registration stock withholds the previous rate qualification;
missing update clocks stay unknown. Upward/downward revisions and true zeroes
propagate automatically; source failures preserve last-good values and clocks.
This repairs an existing observation, not new county coverage, unique-person
validation, an eligible-population denominator or a conditional House bridge.

`data/results-intake/uf-turnout.json` enables the shared collector's
`UF-national-turnout` adapter. It discovers the highest advertised 2026 dataset
edition on UF Election Lab's landing page and follows that edition's declared
CSV and documentation. No future download URLs are guessed. It requires the
reviewed STATUS schema, all 50 states, D.C. and the separate US row, consistent
native counts/rates, matching documentation and retained attribution.

Blank STATUS is estimated even when SOURCE links to an official agency.
Official/Final remain source-reported, not independently certified; unknown
status strings remain unresolved. VAP/VEP are estimated population frames,
not registration stocks. Missing numerators/rates stay null; real zeroes stay
zero. Documentation anomalies remain inspectable. HTTP Last-Modified is a
representation edition, never a native count-update clock.

Same-edition count changes, including decreases, require a strictly advancing
HTTP edition. Advertised successor versions must pass the same identity and
schema checks. Failures retain last-good counts and their original observation
receipt; durable access stops apply before any cache or transport request.

The existing hourly runtime adds these rows to the current count snapshot and
exports `participation/uf-turnout.csv`, `uf-turnout.json` and the complete
`uf-turnout-queries.json`, including both original numerical/documentation
files and source pins. The existing state participation reader consumes this
optional payload; older runtimes retain the explicitly dated saved fallback.
No county/precinct/group allocation, conditional-model promotion or refit is
authorized. Reader source changes require a separately authorized deployment;
this intake does not deploy Pages.

For a selected-source refresh that preserves every other input:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation \
  --ref main -f refresh_sources=UF-national-turnout
```

The complete source download reproduces with
`python -m scripts.results_intake replay --package . --output reproduced`.
The runtime ZIP's `REPRODUCE.txt` specifies its exact producer Python version
and complete offline command. Neither replay acquires election sources.

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
If a withdrawn ranked-choice pending record has a unique, newer, complete,
source-verified final for the same provider contest, the export additionally
links it with `superseded_by_race_id`. Both rounds stay in every complete
query; `superseded_rcv_records` identifies the archived subset of the legacy
`retained` count. This does not certify the result or qualify a swing.

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
The original 2020 regular-seat-cycle Senate baseline binds Class II only;
the reviewed analytical successor below adds complete official, seat-aware inputs.
Native clocks
are source epochs; the election date is explicitly the reviewed national-index
context, not an invented per-race field. Candidate votes are never turnout.

New returns do not replace frozen behavioral-model inputs without a reviewed
candidate/source/frame match. The versioned successor below supplies that match
for compatible existing frames. Existing
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

### Reviewed automatic analytical handoff

#### Comparison-specific House geography

The separately pinned boundary review `20261117-01` replaces the blanket
district hold for supported **2024 House to 2026 House** comparisons. It does
not qualify a behavioral model, participation numerator, legal boundary
certification, or district map. The complete 119th/120th Congress national
Census block-equivalency ZIPs and both complete split-block PDFs accompany
`data/results-intake/district-boundaries/20261117-01/review.json.gz`.

The compiler checks every regional copy against its national member, preserves
leading-zero block IDs, and compares sorted, exact original 2020 Census block
memberships. Equal district numbers are not evidence. Split blocks touching
either district in either edition keep both comparisons held: equal whole-block
assignments do not prove equal split geometry. Colorado 07/08 therefore remain
held. Changed memberships remain held without allocating historical votes.

The selected 120th national BEF incorporates Census's Missouri correction;
the superseded Missouri TIGER geometry is not used. Census's general page
mentions both October 6 and October 7, 2026; its specific BEF page says the
national file was regenerated October 7. Exact original-byte hashes, rather
than an assumed universally consistent documentation date, select the edition.

All 435 voting districts receive a decision: 288 have compatible boundaries,
145 have changed memberships, and two have unresolved split geometry. Applying
the independent candidate/count/stage/round/freshness guards to the retained
hosted run `43933156698` qualifies **259**, previously zero. This reclassifies
retained evidence, not newly collected election observations. House state
comparisons remain 32, Senate comparisons 28, and automatic conditional
House updates AR/TN/VT across nine variants; no frozen model is promoted.

The actual hosted successor `44103888973` publishes **258** qualified district
comparisons using the source checked November 17, 2026 at 04:49 UTC: 432 House
races refreshed, three retained, and all 35 Senate races refreshed. FL-05 is
the sole qualification difference from the older retained-packet proof: the
newer source omits or changes its candidate inventory. Its last-good counts,
original clock and raw arithmetic remain available; the comparison is held.

The identical-input hosted run `44105172617` is a genuine no-op: unchanged
runtime `743b081c`, unchanged data tag, and zero website builds. The complete
285,601,535-byte published archive independently reproduces all 149 outputs
offline, with zero requests; all 17 congressional exports match their full
public downloads. The built reader passes all 435 House rows and 28 Senate
comparisons at desktop and mobile widths, including reviewed FL/OH/GA details.
This is built-reader acceptance using actual published data, **not** a new
frontend production deployment; no Pages deployment was requested.

Complete hashes, all query/download URLs, controlled count corrections, source
freshness, explicit holds and the exact offline command are recorded in
[`hosted-acceptance.json`](../data/participation-access/20261117-house-boundaries-01/hosted-acceptance.json).

Every hourly runtime reapplies these rules to its actual race inventory.
Missing or incompatible returns retain raw changes and explicit holds.
`congressional/congress-house-boundaries.csv` contains all 435 decisions;
`congressional/house-boundary-queries.json.gz` contains the complete reviewed
memberships, splits, evidence pins and decisions. Both accompany the existing
candidate, race, comparison and scientific-eligibility exports and complete ZIP.

To recompile the geographic review using the four packaged originals:

```sh
python3 -m scripts.congressional_geography \
  --originals data/results-intake/district-boundaries/20261117-01 \
  --output /tmp/congressional-boundary-review
```

Use a new output directory. The complete automatic runtime's `REPRODUCE.txt`
specifies its exact Python version and offline command; no Census download or
respondent refit is needed for routine return updates or numerical replay.

#### Candidate and scientific source frames

The reviewed identity successor, `20261117-identity-01`, evaluates the complete
470-race inventory using retained FEC candidate, committee and candidate-committee
linkage tables. It resolves 18 previously ambiguous candidate identities using
stable FEC IDs and literal full names or explicitly authorized committee names.
It does not use a nickname dictionary, surname/initial matching, or FEC filings
as evidence of ballot completeness, election stage or candidate vote counts.
Subsequent hourly returns still must match the reviewed provider IDs, candidate
inventory, parties, source frame and advancing native clock.

Only Delaware clears every remaining compatibility requirement. Together with
Arkansas, Tennessee and Vermont, it can automatically recondition all nine
existing model variants: four states / 36 variant frames, versus three / 27.
The other 29 previously qualified House-state models remain explicitly dated
and frozen. The original 33/17 scientific mask, official Hawaii/Wyoming frames,
all 1,401 legacy candidate records and unresolved aggregate-Other mass remain.
Resolving an identity alone does not remove a separate coverage or model hold.
Senate conditional-model eligibility is unchanged.

Every eligible refresh also updates raw margin arithmetic and common-source-ID
diagnostics in each result's comparison metadata. Those diagnostics retain
their original geography qualification; matching IDs never grants boundary
compatibility. Frozen results keep their own dated counts and diagnostics.

The complete runtime includes the frozen predecessor review, full allowlisted
FEC identity tables, source/schema receipts, identity evidence and reproducible
successor decisions under `data/results-intake/analytical-handoff/fec-identity/`.
Contact/address fields from the original FEC files are excluded. Existing
candidate crosswalk, state/race decision and conditional-result downloads
contain the successor's actual effect, not merely a bridge manifest.
The congressional reader patch explicitly accepts this reviewed version and
rejects unknown future versions; activating frontend source still requires a
separately authorized deployment. This work does not deploy Pages.

The actual hosted identity successor **44125854174** publishes Delaware's
new numerical results, not just its bridge: automatic conditioning increases
from three to four states and from 27 to 36 variant frames. The existing
production House reader matches all nine Delaware variants at desktop and
mobile widths without a Pages deployment. A controlled seven-vote decrease
also propagates through normalization, all nine models, complete exports and
the semantic readers; it is a controlled revision, not fresh acquisition.
Actual hosted rerun **44128294150** reports unchanged and preserves both the
data head and complete manifest byte-for-byte.

The actual 286,877,646-byte immutable runtime ZIP independently reproduces all
152 outputs offline under CPython 3.12. All 64 public model/query bodies and
17 congressional download declarations are verified. Collection freshness is
428 refreshed / seven retained House races and 35 refreshed Senate races;
comparison qualification remains 258 districts, 32 House states and 28 Senate
contests. The undeployed congressional reader still badges 25 Senate
comparisons; production acceptance of the existing House model reader does
not activate that separate patch. Full before/after points, source queries,
download pins, exact commands and remaining holds are in the
[hosted acceptance record](../data/participation-access/20261117-house-identity-automatic-01/acceptance.json).

#### Explicit quoted reference names and authorized candidate designations

The optional `congressional_reference_identity.py` extension resolves the retained
Pennsylvania District 5 Nick/Nicholas identity discrepancy. It requires the
literal full formal name and quoted nickname in the same native candidate cell
as its stable FEC identifier, a separate primary nominating-party page naming
that nickname and district, and the complete existing authorized FEC
candidate-to-committee-to-current-Form-1 chain. It does not infer a nickname
from a surname, campaign hostname, registration alone, or a nickname dictionary.

The selected independent candidate reference is **identity evidence only**,
not official ballot-presence, completeness, vote-count or election-stage
evidence. The safe bounded facts, complete predecessor chain, original body
pins and independent native verification are included under
`data/results-intake/explicit-reference-names/`; full publisher HTML and private
contact/finance fields are excluded. The retained Form 1 facts reuse the earlier
dual-reader/cache binding; a complete historical HTTP receipt was not recovered.

Only the existing PA identity guard is removed. All candidate counts, literal
parties, named minor candidates, Other/write-in mass, historical endpoints,
scientific eligibility and other state decisions are preserved. The top-level
review contract remains the already supported complete-category version; the
identity extension has its own version and pinned, replayed evidence.
Subsequent compatible source revisions automatically recondition all nine
existing variants without another name review or respondent refit. Changed
candidate inventories, stages, source frames, native clocks and missing counts
continue to fail closed and retain the last-good outputs with their own dates.

The controlled retained-source proof advances only PA across nine variants,
then verifies native-source upward and downward corrections, outage retention
and byte-identical no-ops. It supports twelve automatic House states / 108
variant frames and leaves twenty-one previously qualified state models frozen.
This is not new return acquisition, participation observations, empirical
individual-transition validation or a claim that the consumer is already live.
The complete analytical packet includes the extension, all selected evidence,
tests, rolling predecessor and full numerical query set; the documented
CPython 3.12 offline command revalidates the evidence before reproducing it.

#### Explicit primary-source name declarations

The separately reviewed `20261117-declarations-01` successor accepts explicit
same-candidate full-name/nickname declarations from a candidate or nominating
party. It requires the complete preceding FEC identity chain, the same stable
FEC candidate and congressional frame, an exact source role, a full surname,
and a noninitial first-name anchor. Optional single-letter middle initials and
straight/smart quotation marks are supported; a generic nickname dictionary,
initial-only matches and different full middle names are not.

The selected Valencia County Republican Party biographies explicitly supply
Ndidiamaka "Didi" C. Okpareke for New Mexico District 1 and Gregory C. Cunningham
for District 2, whose biography also uses Greg. These declarations resolve two
identity holds, not ballot presence or vote counts. The retained national feed
supplies six candidates across the three districts, totaling D 444,863 /
R 277,531 / Other 0 in the numerical proof. Those are retained-source counts,
not a claim of fresh acquisition or certification.

New Mexico consequently joins AR/DE/TN/VT for automatic reconditioning across
the existing nine variants: five states / 45 variant frames rather than four /
36. The remaining 28 previously qualified state models stay frozen where
independent guards still fail. The 33/17 scientific mask, all legacy candidates,
unmatched minor/write-in mass, protected official frames and Senate model
requirements are unchanged. Each hourly runtime reapplies the reviewed rules;
no assistant approval or respondent refit is needed for compatible revisions.

`data/results-intake/analytical-handoff/name-declarations/` retains the complete
preceding review, safe factual declarations, source/schema receipts and a
separate native verification. The loader recomputes the full evidence chain
before accepting its decisions. Complete runtime downloads embed all six
FEC/declaration evidence files alongside the existing geography originals,
candidate crosswalks, decisions, numerical outputs and literal offline replay.
The congressional frontend accepts only the explicitly reviewed version;
source publication does not deploy that frontend patch.

The predecessor `data/results-intake/analytical-handoff/review.json.gz`, version `20261116-01`,
reviews the complete provider inventory against all 1,401 retained legacy
candidate records and all 50 state decisions. Initial matching requires
district/office/election/stage, literal-party classification and a reviewed
name rule; names alone cannot grant scientific eligibility. Subsequent hourly
revisions use frozen provider race/candidate IDs, literal names/parties/roles,
source URLs and monotone native clocks, not repeated name matching or manual
race approval. Later-clock decreases and zeroes are accepted; missing counts,
new identities, outages, changed party coverage and clock rollback hold the
affected analytical frame.

Descriptive `tabulationStatus` updates can arrive without a changed native
count clock. They refresh the literal source metadata only when every other
normalized and native fact is identical. They neither authorize same-clock
count corrections nor imply certification. The hosted November 16 batch
exposed this distinction in eleven races; the shared revision check now
handles it without race-specific exceptions.

Arkansas, Tennessee and Vermont have compatible complete D/R/O endpoints under
this review. Their subsequent revisions automatically recondition all nine
existing profile/family variants, without fitting respondents. In the retained
real-input proof Arkansas and Tennessee change numerically; Vermont is a genuine
unchanged endpoint. The old 33-qualified/17-held science mask remains frozen.
Under the predecessor review, the other 30 formerly qualified states keep explicitly **FROZEN ANALYTICAL
RESULT** labels, original native clocks and old numerics, separately from
fresh recorded returns. The 17 original scientific holds remain; none is
promoted by the bridge. Arizona alone explains the old 33 versus current 32
state masks: AZ-03 changed major-party coverage. Hawaii/Wyoming retain their
protected official source frames. Other states have specific candidate-name,
new-candidate or unresolved aggregate-Other frame differences in the complete
decision export. An Other bucket is not allocated to omitted candidates:
every old minor-candidate identity/count remains dated and downloadable.

The complete FEC 2020/2022 Senate workbooks and complete Nebraska 2024 canvass
are pinned and included once. Rules select the latest completed **same-seat
final election**, retaining regular/special and general/runoff identities.
This resolves Florida/Ohio Class III, Oklahoma 2022 special, Nebraska 2024
special, Oregon's literal `DEM/IP/WF` classification, and an explicitly labeled
Georgia decisive-runoff-to-final-general comparison. Reviewed Senate swings
increase **24 to 28**: FL/OH/OK/OR/GA resolve, while Louisiana acquires a genuine
prior multiple-nominee hold. Nebraska's prior-seat gap resolves but its current
absent-D hold remains. Remaining Senate holds are AK/AR/ID/LA/ME/NE/SD;
RCV, absent-party and multiple-nominee reasons remain independent.
Before the separate geography successor above, all 435 House district
comparisons remained raw/boundary-held.

The deployed v1 reader can badge only regular Class II, same-stage Senate
comparisons. With **no Pages deployment**, it displays all current counts and
raw changes, 25 compatible badges and an explicit reader-limit explanation
for the other three reviewed comparisons. All **28** qualified comparisons
are in `congress-comparisons.csv` and the existing complete-query download;
seat or stage identities are never falsified to satisfy the old reader.
Existing Senate conditional models remain separately dated: no reviewed
seat/stage/provider-to-prior bridge exists for them.

The existing query link now includes the complete policy/crosswalk, latest
race/state decisions, official seat references, all reviewed comparisons and
all nine complete conditional results. Separate CSVs additionally expose
candidate crosswalks, scientific eligibility, current analytical decisions
and every historical Senate candidate. The same complete runtime ZIP contains
all originals, public synthetic priors, frozen inputs, code and exact outputs.
Ordinary replay uses included compiled native facts; optional regeneration
of official baselines requires the existing `openpyxl>=3.1` and
`pypdf==6.16.0` source-reader dependencies. Neither path refits respondents.

Exact numerical replay uses the producer's Python implementation and
major/minor version, recorded in `inputs/numerical-runtime.json` and the
packet's command. The hourly producer uses CPython 3.12. Python 3.9's different
floating-point summation does not reproduce newly conditioned outputs byte
for byte; the retained hosted packet does reproduce all 147 outputs under
CPython 3.12 with zero requests. New packets reject an incompatible interpreter
before computation rather than weakening numerical equality. Runtime identity
also includes this interpreter declaration.

Readable endpoint labels abbreviate long hashes and spell out hold codes so
they wrap on narrow screens. Full `current_snapshot_identity`,
`last_good_snapshot`, stable provider IDs and literal hold codes remain in
the complete results and decision downloads; no source identity is shortened.

### November 16 reviewed automatic analytical handoff

Actual hosted source **43920096796**, data-only consumer **43933156698**, and identical-input no-op **43933995521** are accepted. **435 House / 35 Senate** races refresh through the existing hourly bulk system. Recorded qualification is **32 House states / 28 Senate contests**, versus 32/24; the unchanged deployed reader badges 25 Senate comparisons and retains explicit reader-limit explanations for FL/OH/GA. All 28 are qualified in full CSV/query exports.

**AR/TN/VT automatically recondition all nine accepted model variants** when compatible counts change; the delivered release numerically changes AR/TN. The final replay/display repair preserves all 450 already-published state/variant numerical results. A diagnosed missing per-family endpoint receipt is also repaired: the unchanged strict live loader now accepts the fresh conditional models instead of falling back to embedded older estimates. Unchanged rolling runs preserve the actual last numerical endpoint's receipt. A subsequent physical screenshot review exposed equal array-valued clocks being rejected by the sensitivity reader. The compact exports now use matching literal clock strings; all full scientific results and original clocks are unchanged. Fresh nine-variant ranges are verified in the unchanged live reader, not merely present in a manifest. The other 30 formerly qualified states remain explicitly dated frozen results, alongside all 17 original scientific holds. Every old candidate record remains. All 435 district comparisons remain raw/boundary-held; Senate models lack a reviewed seat/stage/source-to-prior bridge. Candidate totals supply no new turnout denominator. No respondent refit, Pages deployment or assistant continuation is used.

For example, the original ridge Tennessee model now uses D **896,349** / R **1,095,895**, rather than 903,874 / 1,088,370. Its same-office D-minus-R margin change moves **22.417948 to 21.662519 pp**; modeled switching moves **8.908411 to 8.620090 pp**, and modeled net participation **12.351412 to 11.923061 pp**. These are conditional model components, not observed individual behavior. Full-precision before/after counts and points for all nine variants are included in the coverage/download record.

### Previously delivered collector coverage and verification

Two actual hosted bulk collections, 43879718273 and 43881898831, each
discovered/refreshed 435 House and 35 Senate contests, zero retained/held in
either chamber. There are 1,226 candidate observations: 1,121 House and
105 Senate, with 33 regular and two separate special Senate contests.
No nonvoting House seats are advertised in this particular national inventory.

The first runtime, 43882019877, delivered all 470 contests and 1,226 candidate
counts/parties with exact native clocks. Its identical-input hosted rerun,
43883308494, was an unchanged no-op: same runtime/data commit, zero Pages
builds. The second source collection was different: 27 candidate counts changed
in 14 House races and six further races changed their native clock only.
These are real bulk-source updates, separate from the controlled
House-minus-seven/Senate-plus-eleven propagation tests.

Runtime 43885363583 published that second batch. Independent acceptance
verified all 139 offline outputs, seven public congressional exports, 1,226
candidate counts/parties and 470 native clocks. The actual desktop/mobile
production consumer passed against runtime `196439d6`; both numerical updates
started zero Pages builds. Explicit HTTP-503/checksum failure and real retry,
plus the dated no-JavaScript full-package fallback, also passed.

Recorded qualification is 32 statewide House comparisons and 24 same-seat
Senate comparisons. Eighteen House state and eleven Senate holds remain
inspectable, as do all 435 raw, boundary-held district changes. These are not
the frozen behavioral model's separate 33/17 qualification decisions.
New candidate returns lack a reviewed provider/candidate/source-frame bridge
to that scientific input, and do not supply all-ballot participation or a
compatible group denominator. Existing fits and probabilities are not changed.

The complete source packages reproduce 18 outputs; the complete runtime
reproduces 139, including seven new congressional products. Actual hosted
collector tests passed 688 cases with 11 optional skips and 17 subtests.
The extracted collector suite and canonical installed source each pass
31 congressional behavior tests, including additions, revised/decreased
counts, unchanged data, partial outages, missing candidates, last-good
retention, special seats, runoff and RCV separation.

The existing explorer was updated once for the new consumer. Subsequent
numerical publication is data-only. Its actual Pages artifact preserves all
437 previous complete-download pins, 5,386 previous table rows and three
embedded scientific payloads; actual payload 994,287,197 bytes and raw tar
996,884,480 bytes both remain strictly below 1,000,000,000.
The no-JavaScript/failure fallback is a specifically dated saved complete
release, not a falsely current table; live full download links advance
automatically.

[Complete coverage/download pins](../data/participation-access/20261116-congressional-automatic-01/coverage-and-downloads.json)
and [hosted/offline acceptance](../data/participation-access/20261116-congressional-automatic-01/acceptance.json)
retain actual run IDs and distinguish fixtures, real acquisition, no-op,
offline reproduction and actual production browser verification.

## Supported analytical release and selective recovery

The accepted finite release is source `30bb6e95` / runtime `9c7117fb`.
[Exact coverage and complete downloads](../data/participation-access/20261116-supported-analytical-release-01/coverage-and-downloads.json)
include 18 compressed CSV/query products in the same complete numerical
archive, with native dates, qualifications and explicit omitted-frame reasons.
That preserved version has 132 complete runtime outputs, versus its previous 113;
the congressional successor above has 139.
This increases integrated/exported product coverage, not the number of people
observed or newly qualified comparisons.

The handoff is `results_intake` -> `automatic_native_refresh` ->
`automatic_estimates` -> `automatic_runtime` -> the existing explorer.
The reviewed release adds complete administrative/rate, historical survey,
2026 modeled demographic, recorded/qualified House comparison and conditional
mechanism CSVs to the same runtime archive. Each changed observation has a
source-to-analysis decision explaining which analytical prerequisite is absent.
Existing Senate/governor snapshots and complete queries remain a distinct frozen
product with their own source clocks and qualifications, separate from the new
hourly congressional returns.
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

The reviewed D.C. citywide voter-summary row covers the entire jurisdiction
and its coextensive county equivalent, 11001. The statewide reader mirrors
that existing canonical observation by ID without adding another count. The
administrative query marks `also_covers_full_jurisdiction`; the coverage
table therefore recognizes both scopes, not two independent observations.
The archived unofficial count and same-report registered-voter fraction
remain dated until a compatible official source revision is accepted.

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

The statewide release also preserves the direct `TurnoutData.TotalBallotsCast`
from the November 5, 2026 capture: 893,026, reconciled against all 75 counties
and bound to the original receipt and exact county control vector. Of 2,768
reporting units, 2,761 were fully reported and seven were partial. A sparse
county counter stays blank in the packaged query; it can contribute zero to
the reconciliation only when the other counter accounts for every unit.
The release labels this edition retained and unofficial, reports no rate,
and does not retry the stopped route. A future accepted snapshot of the
reviewed native export can replace it automatically using the same parent
checks; an incompatible parent leaves the prior statewide count in place.

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

### Cuyahoga County, Ohio: full-election participation

The hourly collector follows the county's November 3, 2026 election index to a
uniquely identified countywide results PDF. It requires the complete numbered
page series, matching county/election/scope, and identical statistical headers
on every page. The November 4 unofficial report yields 482,011 ballots and
878,381 same-report registrations (54.87%). The printed clock is report
generation, not a separately verified count-update clock. The count is not a
sum of candidate votes, a complete statewide count, or certified turnout.

This county's report takes precedence in the government-source view and the
local drill-down from the state estimate views. Compatible reports can revise
counts in either direction; incompatible or unavailable reports retain the
last qualified observation. The source packet includes every native
statistical header used by the query.

### Ohio: retained statewide and county participation

The November 13, 2026 unofficial edition reports 4,658,250 counted ballots and
8,018,054 registered voters (58.10%). Both statewide controls match the full
88-county table, and every county's counted ballots, registrations and reporting
counters match the dated XML. Outstanding overseas and provisional ballots are
separate. The XML generation timestamp is not a ballot-count update time;
complete precinct reporting does not establish certification.

When the exact XML route is stopped at acquisition and there is no accepted
statewide predecessor, the runtime can use the checksum-pinned aggregate query
at `data/results-intake/oh-20261113-statewide-and-counties.json`. It does not
revisit stopped routes or treat those observations as fresh. After bootstrap,
the runtime retains the last accepted edition on failure and consumes qualified
revisions from the regular collector. The government-source county view selects
the independent Cuyahoga report and the other 87 records from the statewide
query; do not sum this mixed-edition map to obtain the statewide fraction. The
early and mail activity frames and the existing county geometry are unchanged.
The complete analytical download includes the aggregate input, original source
pins, replay code and all queries. It does not include unrelated XML contest
records or imply any precinct or demographic participation rate.

### Georgia and three county canvasses: retained participation

The Georgia feed edition published November 18, 2026 reconciles **4,218,112
ballots cast / 7,535,442 registered voters (55.98%)** across all 159 counties.
The numerator is a derived statewide sum, not a published statewide parent:
the native statewide ballot field is zero. The same-feed registration fields
reconcile. The statewide feed is unofficial; county status is source-reported,
and per-county update clocks are not a common statewide count clock.

The retained county reports supply Summit, Utah (20,223 / 29,388 pre-election
active registrants), Sussex, New Jersey (57,818 / 112,512), and Douglas,
Wisconsin (19,423 / 26,599). These are countywide, same-report fractions, not
eligible-population estimates or precinct allocations. A report's generation
time is not a count-update clock.

The runtime uses the pinned aggregate files under `data/results-intake/` only
after a recorded acquisition stop on the exact registered route and only if
the corresponding reviewed observation has not already been adopted. The two
existing county selections (Summit and Sussex) must still point to the reviewed
predecessors; an independent Douglas selection is not overwritten. The runtime
leaves early and mail activity in their own frames. Compatible subsequent
reports use the normal revision path; no stopped URL is retried and no retained
edition is marked fresh. The analytical archive contains the full factual
queries, original source pins, and replay code, not publisher PDF or HTML.

### New Hampshire: municipal VotingWorks tally reports

Register a compatible town once in `VOTINGWORKS_TOWNS` in
`scripts/results_turnout_history.py`: the stable feed ID, literal town name,
reviewed municipal feature key, official election index, report link label,
document path convention, and the native election ID. The hourly collector, selected
refresh, analysis, map binding, and coverage export all use that registration.
No new workflow or per-town projector is needed.

The official index must declare exactly one matching report. The document
number and, where declared, a timestamped filename suffix can change without
code changes. A numeric-only DocumentCenter route is allowed only for a
reviewed registration with a date-specific link label. The report must use the
approved HTTPS host and path pattern and pass the same native title, election, town,
edition, and count arithmetic checks. A newer report can correct the count in
either direction. Outages, stops, old editions, and incompatible reports retain
the last-good record. Image-only layouts are not auto-qualified.

Hollis's retained report supplies 5,005 ballots (4,977 scanned and 28 manually
entered), no registration denominator, and no count-update clock. Report
generation time is separate. The match to the pinned 2024 municipal reference
is contextual, not a 2026 precinct boundary. Complete factual queries and
source pins are packaged; signatures and original municipal PDFs are not
redistributed. Use the existing `refresh-selected` command with
`NH-hollis-municipal-turnout`.

The same collector handles Bedford's timestamped official report (11,766
ballots) and Hanover's numeric-only declaration (5,592 ballots). Neither
source supplies a matched denominator or native count-update clock.

### Minnesota: statewide count from complete precinct statistics

The hourly collector reconciles the statewide reporting page against the
statistical TXT by all 87 native county IDs. A statewide count requires
complete precinct statistics and agreement on every county's total number
voted, precinct inventory and 7 a.m. registrations, not just agreement on a
statewide sum. The two retained products agree on 2,851,615 in 4,105 precincts.
The source's printed result status and update label are retained. The page's
separate turnout percentage uses a UF electorate estimate; neither it nor the
7 a.m. registration figure establishes a qualifying administrative rate.

### Washington: general-election turnout table

The collector polls the Secretary of State's statewide turnout series.
The complete table is included in the source queries and exported as
`queries/model-queries/participation/washington-general-election-turnout-history.csv`
in the analytical archive. A missing 2026 row means not yet published, not
zero turnout. A new 2026 row qualifies a statewide count directly; its
registered-voter rate is calculated only when the printed percentage agrees.
The source does not establish a native count clock, certification, or county
or precinct totals. If the current row disappears, the last qualified count
is retained and labeled accordingly.

### Alaska: statewide Voters Cast

The collector checks the complete summary PDF against both federal
participation controls in the public statewide feed. For November 18 the
standalone header shows 290,323 Voters Cast / 605,433 registered (47.95%),
unofficial. The PDF says 401 of 401 reporting precincts; the statewide feed
says 401 of 403. Both inventories are preserved. No completeness, unique
voter, or substate result is inferred; the same-report fraction remains valid
for the reported counts. Candidate selections and contest scopes are not
added or substituted for the statewide parent.

### Virginia: certified-series statewide participation

The same history-table collector reads Virginia's November General Elections
series starting in 1976. The archive exports all six native columns, including
the absentee missingness and registration change notes, plus the rate audit.
The Department adds annual rows after certification. A new 2026 `Total Voting`
row will populate the statewide view without substituting candidate totals or
the live API's conflicting zero. The same-row `Total Registered` includes
active, inactive and overseas voters; no local or demographic rate follows.
