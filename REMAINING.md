# Remaining work: participation and election-transition estimates

Updated: 2026-11-08 UTC. Source catalog: [SOURCES.md](SOURCES.md).

**The project is not finished when the files are downloaded.** Acquisition and
reconciliation must feed the participation, switching, modeled/reported
nonparticipation and new/returning-voter estimates, then their tested integration
into the existing project. Do not stop at an inventory or another audit.

The user explicitly restored a 15-minute assistant continuation on this date.
It must read this file and the source ledger, update actual progress, and continue
downstream work. Older notes saying the prompt is stopped are superseded.
This document itself does not install a cron job or enable a website workflow.

## What is already held

| Input | Actual state |
|---|---|
| MEDSL 2022 national originals | All 51 jurisdiction ZIPs acquired and checked; 12,310,863 native rows. Precinct gaps and reconciliation holds remain, not blanket nationwide completeness. |
| MEDSL 2024 national originals | All 51 ZIPs and three aggregate CSVs acquired and checked; 18,383,653 native rows. Same source/geography caveats apply. |
| NYT 2024 precinct layer | Existing saved presidential results/geometry for 49 states plus D.C.; Alaska and within-state omissions explicit. Not a demographic voter file. |
| NYT 2020 precinct layer | Existing original layer for 46 states plus D.C.; not a cross-year boundary panel. |
| Historical county returns | Large existing candidate compilation plus official controls and reviewed historical House subset. Discrepancies remain explicit. |
| AP/NORC survey files | Supplied 2018/2020/2022/2024 archives, codebooks and questionnaires privately inventoried and qualified. Duplicate 2022 copies are one sample. |
| Civic 2026 survey | Actual supplied 113,020-row, 50-state file and codebooks held and privately checked. No D.C.; core model/intention/recall definitions identified. |
| Combined county JSON | Pinned complete 3,143-entry snapshot held: 3,111 `h26` records, 3,083 paired `h24/h26`, 2,443 `s26` records. Alaska/Connecticut records require explicit exclusions or repair. |
| Governor comparison CSV | Complete Karl Rohe source held: 2,014 records; native state/geography/count review still required before joining. |
| Pushbuild 2026 national snapshot | Complete 40-state CSV snapshot acquired: 127,870 source rows; all 42 Git blobs and ZIP integrity checked. Native results and candidate-list placeholders are distinguished. |
| Both exact Senate feeds | All 35 civicAPI and all 35 CNN files acquired successfully, plus the full Transparency Cascade CSV. Initial candidate-count checks below are computed, not merely planned. |
| Civic numerical estimates | Computed for all 50 states plus a separately labeled pooled-source scope: 1,954 participation rows, 97,700 complete joint cells, 3,908 signed decompositions, and 30,782 separate likelihood cells. Independent native verification passed 246,204 checks. These remain private exploratory/source-weighted estimates, not administratively validated turnout. |
| New descriptive House comparison | Complete 3,143-row query saved; 3,083 positive-vote pairs, 2,776 comparisons after known-source screens. Native exact Pushbuild House subset: 8,509 candidate rows in 35 states; 702 candidate county sums match their source state control. Rounded-share comparisons and exact candidate counts remain separate. |
| Exact historical/current House join | Computed from actual county-district-candidate inputs: 3,152 county records, 2,639 positive-count pairs, 2,228 passing known-source screens in 38 states, and 5,192 county-district records. Independent native verification passed 124,804 checks. The complete 1,466,353-byte, 18-member ZIP and all seven supplements are published immutably; nine tests and two network-blocked, byte-identical reproductions passed. |
| Existing current counts | National preliminary state turnout estimates, a 49-state exact county House snapshot, and selected primary state/local participation observations already exist. Reuse them. |
| Existing live maps/safeguards | Reported state-outline/map fixes and unsupported-population-estimate safeguards are already live. Do not reopen completed map work as a substitute for research. |

Originals, qualified aggregate queries, source receipts and exact pinned commits
are recorded by source family in `SOURCES.md`. Source possession does not mean
every comparison or redistribution is approved.

## Execution queue

| Priority / task | Status | Required result |
|---|---|---|
| 1. Download Pushbuild national CSV snapshot | Acquired and byte-verified | Complete pinned archive and all 40 state CSVs held; proceed to candidate/count/geography controls. File presence is not county coverage. |
| 2. Acquire all declared Senate race files | Acquired | All 70 race responses plus national index, original comparison CSV and receipts held. No more duplicate acquisition is needed for this snapshot. |
| 3. Reconcile exact 2026 returns | Initial Senate checks computed; gaps open | 34,492 native candidate-unit rows retained. Civic county/parish/city selection yields 2,442 records/34 states, six missing FIPS; 7,165 cross-source candidate counts equal, 215 differ. Four RI gaps resolve to the explicit 755-vote Overseas/Federal unit, not county allocation. Of 234 civic candidate controls, 229 now reconcile, four AK noncounty controls are held, and the ME 882-write-in county gap remains. Preserve all unmatched keys/clocks. |
| 4. Build the actual 2024-to-2026 House panel | Exact source-count join computed, independently verified and published | Complete 3,152-county/5,192-fragment query, including all 2,639 positive pairs and 2,228 known-screen passes. Preserve all exclusions; same district labels do not establish matched boundaries. Next qualify remaining source/control and boundary exceptions and use the exact contest context alongside actual participation controls, not as measured turnout. |
| 5. Finish five-wave survey numerical outputs | Computed and independently verified | Civic plus AP 2018/2020/2022/2024 tables now exist. AP covers 532,866 native rows and 12,024 aggregate rows across all four source weight frames; 132,196 independent count/weight/rate checks passed. Preserve the 2018 inference qualifier, 2022 DE/WV holds and absent 2022 RACETH5. Historical public selection/presentation remains next; do not re-download or repeat these successful reductions. |
| 6. Reconstruct the margin-change components | Civic computed and independently verified | Both 2024-President-to-modeled-2026-House and 2022-House-to-modeled-2026-House have switching, modeled nonparticipation, no-prior-contest-vote entry, other, unresolved and denominator components. All 714 separate demographic partitions reconcile. Do not call these original-coalition population or causal persuasion estimates. |
| 7. Tie returns and participation controls to estimates | Pending panel and survey outputs | Compare source-weighted survey estimates with observed contest/participation counts without pretending outcome calibration is independent validation. Report unmatched scopes, conditional scaling and sensitivity instead of fitting away discrepancies. |
| 8. Integrate and verify supported estimates | Civic live and exact-production verified; historical AP presentation next | Maintained Civic/AP code is in the research source tree. Civic complete 98,019-byte aggregate ZIP and four CSV supplements are published immutably. Main `96cc899`, Pages run `42438745610`, attempt 1 and fresh artifact `13600852929` passed exact uploaded/deployed identity; actual payload is 997,445,043 bytes and tar is 999,956,480 bytes. All 13 production browser modes passed; HTML, served scripts and county/precinct/source-review pointers match the tested build. All 1,047 prior downloads and IDs remain, plus five full Civic assets. Historical AP public selection/presentation remains next. Do not add front-page experimental clutter. |
| 9. Close statewide historical/2026 holes | Ongoing, alongside estimates | Actual ballots-cast controls, group denominators, histories and matched geography. Do not wait for universal administrative validation to produce explicitly assumption-labeled estimates. |
| 10. Add additional source-supported precinct detail | Secondary to national/state work | Reuse existing Minnesota/Hawaii/Wyoming originals first; get missing whole-state releases/layouts rather than restarting county-by-county research. Local leads below are useful additions, not the critical path. |

No delegated collector/reconstruction output is currently assumed complete.
The initial three jobs failed before execution and are being recovered directly;
do not wait for them or describe them as running.
Direct recovery has now produced the actual downloaded/reconciled/numerical
artifacts above; it is no longer waiting on a replacement agent.

The newest complete private outputs are `survey-reconstruction-all-states-20261108-01/`,
`national-house-comparison-20261108-02/`, and
`senate-cross-source-reconciliation-02/` in the active session artifact workspace.
The House `01` draft and initial Senate `01` queries are preserved; use the stated
successors. The tested portable Civic code is now maintained in the project;
disclosure-reviewed Civic aggregate delivery is now published as immutable release
`participation-civic-estimates-20261108-01`. Its integration into the existing
default-closed research view is now live and exact-production verified.
The corrected four-wave AP numerical outputs are
`ap-votecast-participation-estimates-05/`, with independent proof
`ap-votecast-four-wave-independent-verification-01.json`; earlier AP drafts are
preserved but are not the current verified schema.

The exact House result is `house-exact-panel-20261108-03/`; `01` and `02`
are preserved predecessors. All seven numerical query files are byte-identical
to the independently verified `02` result; `03` adds the complete offline
reproduction interface. The full public download is
[immutable House release](https://github.com/hanshanley/margin_of_error/releases/tag/participation-house-exact-panel-20261108-01),
not a metadata-only inventory. `scripts/house_panel.py` preserves all 11,782
historical source rows (including six withheld), all 12,405 current county
candidate rows, 34 historical no-ballot records and all 1,418 current candidate
controls. Of those controls, 1,375 match arithmetically within the same source,
18 have differing located/district scopes, seven lack located county rows,
and 18 lack a matching provider district candidate. These are not independent
outcome validation. All affected county comparisons remain screened out.

The accepted Pages tar has only 43,520 bytes of headroom under the strict
1,000,000,000-byte cap. A later automatic research snapshot has legitimately
advanced the underlying source repository; it was preserved in the House
source-only publication rather than reset. The next website increment must
measure its actual full build against current source context, keep large
complete downloads external and preserve every old route. The accepted Civic
artifact is not a size guarantee for a future build.

## Reconciliation holes that must remain visible

- **Alaska:** statewide and state-House-district reporting is not county reporting.
  Never store statewide history as an apparently valid Anchorage county result.
- **Connecticut:** nine planning regions and the historical eight counties differ;
  the supplied combined builder duplicates some planning-region totals. Repair
  with actual same-geography inputs, not division/allocation of duplicated values.
- **Senate:** 2020-to-2026 regular same-seat comparison differs from Florida/Ohio
  special elections and from 2024-President-to-2026-Senate context.
- **Reporting hierarchy:** county, town and township rows can coexist. Select one
  valid reporting level per aggregation; retain all unused rows with reasons.
- **Missing identifiers:** keep missing FIPS as unresolved rather than inventing
  matches. Names alone do not prove geography or candidate identity.
- **Uncontested/independent/fusion/RCV:** preserve literal choices and rounds;
  do not force every contest into a uniform Democratic-versus-Republican race.
- **Source timing and dependence:** disagreement across snapshots is recorded,
  not overwritten. NYT/civic-derived secondary products are not independent checks.
- **Participation:** candidate votes, expected votes, returned envelopes, accepted
  ballots, counted ballots and credited voter histories are different measures.

## Survey estimation contract

Use the actual supplied files now, with their source-specific limitations:

1. Retain the full registered/source frame and all model-voter/nonvoter and
   unknown categories. A current-voter-only subset cannot estimate full-frame
   nonparticipation. Nonmissing intended choice is not proof of completed voting.
2. Keep recalled 2024 presidential nonvote distinct from no 2024 ballot,
   first-ever voting, first general election and new eligibility.
3. Use documented AP state/national weights and state exclusions. The 2018
   publisher reports electorate estimates for 47 states despite respondents in
   all 50; 2022 Delaware/West Virginia are national-only. Do not infer inference
   validity just from positive weight mass.
4. Civic `CHEP_WEIGHT` exploratory conditional/source-weighted results may proceed
   while its exact target/calibration/field-period metadata remain unresolved.
   Do not relabel pooled source estimates as nationally representative or the
   model's nonvoters as administratively measured people staying home.
5. Prior/current choices are actual joint questions, not products of unrelated
   marginals. Preserve routing, forced hypotheticals, unknowns, other choices
   and native disclosure codes. Do not fit the current electorate to its old
   partisan composition.
6. Normalize margin contributions correctly:
   `Delta(M/T) = mean(1/T)*Delta M + mean(M)*Delta(1/T)`.
   Keep the denominator term; do not divide raw-vote components by a margin-point
   swing or force all shares between zero and one hundred.
7. Raw survey weight units are not people. Any population bridge needs an explicit
   matched denominator and scaling assumption. Death, migration and eligibility
   components are unknown unless measured, not silent zeros.
8. Use separate source-native demographic dimensions first. Do not invent
   respondent county/precinct geocodes or allocate state survey estimates locally.

## Additional supplied sources to pursue, not forget

| Source / hole | Next action |
|---|---|
| MIT county presidential DOI `10.7910/DVN/VOQCHQ` | Recorded native denied route stays stopped. Keep this specific acquisition gap explicit; use distinct already held official/MEDSL sources where suitable, not a bypass. |
| CES cumulative DOI `10.7910/DVN/II2DB6` | Qualify native metadata/guide and earlier-year participation/choice fields before extending pre-2018 survey history. Reuse already held CES common/panel inputs for their existing years. |
| 2026 CES | Record the actual published team delivery schedule and public-release status; do not wait for a future file before using Civic 2026 now. |
| ANES cumulative file | Separately supplied historical lead; review permitted native access and measurement/weight definitions. Earlier denied ANES route is not permission to bypass it. |
| Minnesota statewide precinct House + turnout + layout | Deduplicate against current saved MN packages; acquire only missing/new whole-state originals and reconcile precinct/counties/ballots separately from House votes. |
| Hawaii statewide `media.txt` | Reuse current/historical originals if already held; otherwise freeze complete native text and layout, preserving mail/in-person/ballot definitions. |
| Wyoming official statewide county reports | Reuse previously qualified reports and anomalies; acquire missing precinct returns only where genuinely new. |
| Wayne MI, King WA, San Mateo CA, Monroe FL | Recorded native download/portal leads; check existing originals and relevant releases first. Do not turn optional local detail into a nationwide bottleneck. |
| EAVS / state ballots / registration-history inputs | Statewide/bulk matched controls, original frames and completed histories; requests/access limits handled explicitly, not missing-as-zero. |

## Completion and publication rules

An increment is complete only after its intended output, not merely its source
inventory, is persistent and verified. Keep `SOURCES.md`, this queue and actual
query/manifests consistent. Completed successful source reductions are reused;
do not repeat huge checksums, fits, builds or browser campaigns just for activity.

Preserve all old complete downloads and immutable versions. Raw respondent/voter
records, IDs, private fine cells and individual scores remain private. Public
results need a complete permitted aggregate query/code/results package, not just
metadata. Large new packages stay on verified external immutable delivery rather
than breaking the website's strict actual payload and tar limits.

Preserve unrelated dirty work and the real Git index. Source documents alone
need no full website rebuild. UI changes require focused tests, existing checks,
build and exact live-source/browser acceptance before being called deployed.
