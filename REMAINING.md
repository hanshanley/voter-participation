# Remaining work: participation and election-transition estimates

Updated: 2026-11-10 UTC. Source catalog: [SOURCES.md](SOURCES.md).

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
| Wyoming official statistics, 1978-2026 | New distinct August 2026 primary/general table acquired and qualified: 50 native rows, 50 selected-control comparisons and 48 same-type changes, with a complete immutable 13-member package and all five full assets. Seven tests, 1,220 independent checks and two byte-identical offline reproductions passed. Day-before registration excludes Election Day registrants; 2026 general cells remain blank and the 2024 primary percentage disagreement remains. No election-time R, demographic estimates or new website view inferred. |
| Held EAC historical state controls | Complete immutable release `438401507`: 561 state/year rows, all 15 native/held observations, nine qualified source-defined participation references, six separate Alaska AP/register scenarios, all 602 survey decisions and ten adjacent snapshot comparisons. Eleven exact original registration joins, ten tests, 11,326 independent checks and two byte-identical blocked-network reproductions pass. All nine full assets verified anonymously; the complete 192,220,123-byte ZIP includes every sufficient original/input/query/code/test. All proxy, scope and missingness holds remain. |

Originals, qualified aggregate queries, source receipts and exact pinned commits
are recorded by source family in `SOURCES.md`. Source possession does not mean
every comparison or redistribution is approved.

## Execution queue

**Current priority: actual 2026 county/precinct coverage on the website.**
**Latest accepted live: all37 native ward references in four NH cities.** Source `128c867`
preserves every earlier count/feature and adds six direct state-published2022
ward references, without repairs, allocations or rates. Full17 PDFs/219 pages,
all160 sufficient inputs and every earlier184 archive member remain in the
98,854,240-byte /233-member complete packet. All213 tests/Astro/build, actual
NH desktop/mobile all-six-ward clicks/Methods/tabs/zoom/source guards/retry,
preservedMA307 andall51 navigation pass. Independent3,031checks/two exact
network-blocked five-generation reproductions pass, including16Python/16Node
tests each. Immutable **440231597** / all14 full assets were anonymously
verified before main. Actual Pages **42801350131 attempt1** / guard
**42801349742** succeeded; artifact **13756916795** passes **995,709,635 payload /
998,287,360 tar bytes**. All47 exact unqueried production files and NH37
desktop/mobile, preservedMA307, Illinois102, Alaska81, Maine480, Hawaii4 and
all51 browser suites pass; all436 full-download routes remain unchanged.
Deployment succeeded first try; its bounded same-artifact retry was skipped.
**Do not rerun successful acquisition, preparation, packet, build or acceptance.**
Next, integrate the already-held Minnesota follow-up in a separate new version:
84 complete counties, three partial subtotals and26 unreported native precinct
rows. Preserve the native November7 clock, unknown timezone, component conflicts
and separate Estimated Voters figure; no new acquisition or exact statewide
total is needed or approved. Nationwide precinct completeness remains open.

**Earlier accepted live: 307 direct Massachusetts reporting references.**
`f0156f8` retains every native count and uses all 32 original city-declared
Somerville polygons to close four former holds without clipping. Exact native
WKT, duplicate IDs and source metadata2023/2020 Census basis remain explicit,
not rounded EPSG2249 or certified2026 geometry. Boston275 and the reused
350 valid municipal shapes/Wayland hold are unchanged. The full
22,398,610-byte /146-member ZIP contains all84 sufficient inputs, four full
PDFs/648 pages, full cityZIP, all99,980 pairs and exact offline code.
Immutable **440187428** / all16 full assets were anonymously verified before
main. All211 affected tests/Astro/build/actual MA desktop-mobile four-join
clicks/navigation/Methods/zoom/source guards/retry/all51/NH31 and3,194
independent checks/two exact offline reproductions pass.
Actual Pages **42794958168 attempt 2** / main guard **42794958425** succeeded.
Artifact **13751979967** passes both caps: **995,458,357 payload /
998,031,360 tar bytes**. All45 exact unqueried production files and MA307
desktop/mobile, NH31, Illinois102, Alaska81, Maine480, Hawaii4 and all51 browser
suites pass. First file-sync timeout retained; failed-job-only recovery reused
the same verified artifact with no rebuild or redownload. **Do not repeat the
successful acquisition, package, build, release or production acceptance.**
The six separately qualified direct Dover references are now accepted above.
Nationwide precinct coverage
remains open; do not treat this two-city increment as statewide completion.

**Earlier accepted live: Massachusetts native local counts and references.**
`5432c4a` adds Boston/Somerville native counts, all 307 reporting rows and 303
unchanged reference joins. Four split-parent count joins stay table-only;
350 of 351 original municipal shapes are valid, with Wayland held unrepaired.
Distinct count fields, zero registers, source disagreements and status labels
remain literal; no unique-person count, county allocation or rate is inferred.
The complete 21,432,354-byte / 100-member ZIP contains four full PDFs / 648
pages, all 67 sufficient inputs and 99,484 pair decisions. Immutable
**440115869** / all 14 full assets were anonymously verified before main.
All 205 tests/build/local desktop/mobile/all51/preserved-NH31 checks and two
exact blocked-network reproductions pass. Actual Pages **42784448706 attempt 2**
/ main guard **42784448671** succeeded. Artifact **13748107256** passes both
caps: **995,165,787 payload / 997,734,400 tar bytes**. All 43 exact unqueried
production files and MA desktop/mobile, NH31, Illinois102, Alaska81, Maine480,
Hawaii4 and all51 browser suites pass. The first file-sync timeout is retained;
failed-job-only recovery reused the same verified artifact, with no rebuild or
redownload. **Do not repeat the successful package, build, release or acceptance.**
The four split-parent joins are resolved in the separate accepted source above.
Nationwide precinct coverage remains open,
and little Pages payload headroom remains.

**Earlier accepted live: four city sources and 31 mapped wards.** `a7cd4a5`
adds nine adopted Nashua ward references to Manchester's 12 and Concord's 10.
All earlier counts, source disagreements, separate federal-only counts and
436 complete-download routes are unchanged. Release **440041905** includes
the full 97,907,540-byte archive, 17 PDFs / 219 pages, 140 sufficient inputs
and every mapped/held decision; all 13 assets were verified before main.
Local tests/build/browser checks and two independent offline reproductions pass.
Pages **42773036449 attempt 1** / main guard **42773036375** succeeded.
Actual artifact **13742538594** passes **989,504,509 payload / 992,071,680 tar
bytes**; all 38 exact unqueried production files and NH31 desktop/mobile,
Illinois102, Alaska81, Maine480, Hawaii4 and all51 browser checks pass.
**Do not repeat the successful package, build, release or acceptance.**
Six Dover wards remain table-only; do not use keys, parcel allocation or
unsupported boundaries. Native precinct coverage nationwide remains open.
Massachusetts's independently city-published sources are now qualified in the
separate publication above. Its denied state statistics hub and absent provider
product remain stopped.

**Earlier accepted snapshot: four city sources and 22 wards:**
`d7e6664` adds ten direct Concord ward joins summing to printed19,234 while
preserving all242 source fields /37 ward rows /12 Manchester features.
The complete **97,239,222-byte /160-member** package has all17 PDFs /219 pages,
124 sufficient pins, all22 reference decisions,45 Concord pair decisions and
15 remaining ward holds. Immutable **440018547** / all12 full assets were
anonymously verified before main; source guard42769025074 passes.
All200 focused checks/Astro/build/local desktop/mobile/both-city selection/
zoom/resize/Methods/source guards/retry/all51 and934 independent checks/two
exact blocked-network three-generation reproductions pass. Current municipal
context, not certified2026 legal precincts; source counts/overlaps unchanged,
no rates or geographic allocation. Fresh Pages **42769170439 attempt1** /
main guard **42769170432** succeeded. Actual artifact **13740844615**
passes **989,278,818 payload /991,846,400 tar bytes** and all36 selected/exact
unqueried production files. Actual NH four-city/22-ward desktop/mobile,
both-city tab selection/zoom/resize/Methods/source guards/retry,
Illinois102/Alaska81/Maine480/Hawaii4/all51 production browsers pass.
All436 old complete routes remain. **Do not repeat this successful package,
source, build, release or production acceptance.**
That snapshot's nine Nashua holds are resolved in the separate 31-ward source
above; keep its original failed backend record and immutable release unchanged.

**Earlier accepted live: four New Hampshire cities and12 Manchester wards:**
`5fd7549` retains all four city sources and adds 12 native Manchester ward
totals on current official municipal context (2022 GIS / lines effective
December 21, 2021), not certified 2026 legal precincts. Other 25 ward rows
remain in tables; the default state view is still four-city context.
The complete **94,979,235-byte / 122-member** ZIP retains all16 PDFs /218 pages,
93 input pins, all242 prior fields/37 rows and every native count/reference/
overlap/hold decision. Immutable **439988155**, all11 assets anonymously
verified before main, is published. All198 tests, post-viewport-fix143UI/
Astro/build, actual desktop/mobile counts/zoom/resize/tab selection/Methods/
source guards/retry and finalall51 pass. Independent4,506checks / two exact
network-blocked reproductions verify all3,789 vertices and unchanged prior
queries. Fresh Pages **42763626040 attempt1** / main guard **42763626097**
succeeded. Actual artifact **13738453245** passes **989,164,442 payload /
991,733,760 tar bytes**, all34 selected and exact unqueried production files.
Actual NH four-city/12-ward desktop/mobile counts/zoom/resize/tab selection/
Methods/source guards/retry, Illinois102/Alaska81/Maine480/Hawaii4/all51
production browsers pass. All436 old complete routes remain unchanged.
**Do not repeat this successful package/build/release/acceptance.**
The earlier four-city-only failed run below remains historical; its website
outcome is now satisfied by this distinct combined publication, not an old retry.
Continue the 25 remaining already-held ward rows through separately qualified
current references; never substitute unqualified boundaries or infer rates.
Nationwide native precinct coverage remains open.

**Historical four-city-only deployment failure:** source `9b922c4`
adds already-acquired Nashua/Dover to the accepted Manchester/Concord view:
four cities, 37 table-only wards, 242 source fields and 255 unknown contextual
areas. The complete **93,099,445-byte / 91-member** package retains every
earlier value/original and all15 PDFs /217 pages, plus all28 accounting /
18 printed-basis /259 reference decisions. Immutable release `439947616`,
all ten assets anonymously verified before main, is published.
All192 tests/Astro/build/local desktop/mobile/source conflicts/native-date/
register definitions/mode exclusions/Methods/retry/all51, 1,006 independent
checks and two exact network-blocked reproductions pass. All four selected
context shapes are valid unrepaired/interior-disjoint. Main guard
`42756293648` passes. Actual artifact `13735453505` passes
**989,109,680 payload / 991,672,320 tar bytes** and 32 selected-file checks.
Pages `42756293558` failed three deployment-only attempts at its actual
ten-minute timeout, retaining the same successful build/artifact/native ZIP.
At that failure, exact unqueried public script/NH data still matched the
accepted two-city `452e4c9` version. **That run has no production acceptance;**
the later combined publication above is now live under its distinct source/run.
Retries are stopped; preserve the artifact/proofs. Do not repeat successful
sources, freezes, packages, builds or local tests for activity.

**Earlier accepted live: New Hampshire** source `452e4c9`
connects Manchester's 12 ward packets and Concord's native city report:
two city snapshots and 22 table-only wards on full 259-area 2024 municipality
context; 257 unknown areas remain unknown. Manchester's derived 38,562 sum
retains the 85-ballot Ward 7 discrepancy and separate federal-only 76.
Concord's native 19,234, school splits, opening/EDR/closing registers and source
percentages stay separate; all analysis rates remain null.
Complete 81,359,216-byte / 62-member package includes all 13 full PDFs,
107 source / 259 reference / 12 accounting / 11 printed-basis queries,
code/tests/results. All 188 tests, Astro/build, 778 independent checks,
two exact blocked-network reproductions, desktop/mobile counts/retry/Methods/
unsupported-mode exclusions and all51 navigation pass.
Immutable release `439928692`, all ten full assets anonymously verified
before main, is published. Pages `42752839549` attempt1 / main guard
`42752839324` succeeded; actual artifact `13734333285` passes
**989,103,993 payload / 991,662,080 tar bytes**. All **32 exact unqueried
production files**, NH desktop/mobile counts/22 wards/source conflicts/
unknown-area clearing/unsupported modes/Methods/false-reference retry,
Illinois102/Alaska81/Maine480/Hawaii4/all51 pass. All 436 old complete routes
remain. Do not repeat this successful acquisition, freeze, package, build,
publication or acceptance. Nationwide native precinct coverage remains open.

**Previous accepted increment:** Illinois `09eff27` adds
explicitly contextual activity for all 102 county-named source records per
mode, without whole-county or source-authority-territory claims. All six
city-named records remain separate and visible, never assigned or added into
counties. Native early/returned parents reconcile independently; no rates or
native election-ID qualification are inferred.
Complete immutable release `439900272` is 1,102,066 bytes / 19 members, with
all216source/all204reference/twoframe decisions, both originals, full unchanged
reference/code/tests/results. All eight assets were anonymously verified
before main. 2,814 independent checks/two exact EPERM-blocked reproductions,
182 affected tests/Astro/build/local desktop/mobile/both-mode102/sixcities/
Official exclusion/scope guards/Methods/retry/all51 pass. The retry fix restores
source selectors as well as geometry after a malformed frame.
Pages `42747433131` attempt1 / guard `42747433393` succeeded; actual native
artifact `13731489436` passes **989,037,557 payload / 991,600,640 tar bytes**.
All 30 exact unqueried production files, desktop/mobile/both-mode102 and six
city records, whole-county rejection/retry/selectors/Official exclusion/
Methods, Alaska81/Maine480/Hawaii4/all51 navigation pass. All 436 old complete
routes remain. Do not repeat this successful package/build/release/acceptance.

**Previous accepted increment:** Alaska `3bba8bb` connects 81 native
geographic House-unit counts / 38,672 `b` ballots to valid unrepaired official
26GENR app-reference shapes. All 402 shape decisions and 523 count records
remain; 321 topology holds, 120 pooled district units and one federal-overseas
unit are never repaired or allocated. This reference is not certified legal
geography and no full-election precinct turnout rate is inferred.
The complete 1,385,095-byte / 32-member supplement passes 10,055 independent
checks, two exact network-blocked reproductions, 176 affected JS/four Python
tests, Astro/build, desktop/mobile81 and all51 navigation. All 436 older
complete-download mappings remain exact. Immutable release439872282/all eight
assets were anonymously verified before main. Pages `42742241487` attempt2 and
guard `42742241464` succeeded. Actual artifact `13729439177` passes
**989,017,669 payload / 991,580,160 tar bytes**, 29 exact unqueried production
files, Alaska81 desktop/mobile/all values/source clocks/failure-retry,
Maine480/Hawaii4/all51 navigation. Deployment1 timed out in `syncing_files`;
only its failed deployment was retried, with the original artifact retained.
Do not repeat the successful build, archive, downloads or acceptance.

**Illinois source-scope qualification:** The held feed has 108 source regions per separate
early/returned mode: 102 county-named candidates and six city-named regions.
All source-category parents reconcile; cities are not automatically county
counts or assigned to a single county. Qualify an explicitly contextual
source-region display without whole-county claims, or independent source
hierarchy; keep every city record and all holds. The two official
ElectionAuthorities.aspx / ElectionAuthoritiesPrint.aspx routes returned403
on November10 and are stopped, with no alternate client/cache/mirror.
MA/NH provider responses are absent in this held snapshot; Alaska's provider
responses are state-only. Do not invent regional values from them.
County contest-only fallbacks remain where no qualified participation scope
exists; Illinois has explicitly limited source-region activity, Alaska has
the partial native precinct map, and New Hampshire's two-city integration
remains partial rather than statewide coverage.
Nationwide native precinct coverage remains open.

**Source work already completed for the current extension:** Nashua: 29 pages /
8,349,293 bytes, all nine wards' 36 native fields directly reviewed; retain
three source-accounting disagreements, literal red amendments and separate
federal-only counts. Dover: one page / 125,447 bytes, all 99 fields independently
parsed and visually checked; native 15,941 ballots / 22,456 source registrations,
including 1,484 Election Day registrations, with explicit percentage basis.
Its filename says2025 but the actual report identifies November3,2026.
The canonical official `www` page and declared file succeeded with normal TLS;
the failed bare-host certificate observation is retained, not overridden.
Registration-affiliation stocks are not ballot choice or group turnout.
The separate complete four-city package and local tested integration are
already finished as above; its three deployment failures are explicitly
recorded, not treated as live acceptance. Never alter/rebuild the frozen
releases or reacquire those successful PDFs.
Rochester's independently published official city news is reachable,
but its linked full-results page returned403 and stays stopped.
Worcester remains contest-only, not inferred ballots. Existing state-route
holds stay stopped; private discovery HTML/session state is excluded from
public packages. Nationwide native precinct coverage is open.

**Next active implementation: Manchester native ward reference.** An independent
worktree based on `9b922c4` avoids modifying the four-city acceptance snapshot.
The city-declared service's actual REST Ward layer is3, not WMS ordinal0;
complete native count/IDs and all12 aggregate polygons are held. No personal
official fields or old population attribute was requested. Current clerk
declaration and complete citywide map identify lines effective December21,2021;
the native GIS layer is `Wards_2022`. All3,789 vertices match the server's
geographic output; all12 single-ring polygons are valid without repair.
Six native boundary overlaps, at most16.6606 projected square metres
(2.65335e-6 of the smaller source ward area), remain explicit and unrepaired.
All12 literal ward count joins total38,562, retaining Ward7's85 discrepancy
and separate federal-only76; no denominator is inferred.
Ninety-three sufficient inputs are frozen once; four focused Python tests
pass. The 47,443-byte ward display gzip and additive source registry are
prepared locally, **not committed, UI-tested, packaged or live**. Finish
strict ward-reference guards/labels, browser acceptance, complete originals/
code/queries/results and authorized publication. Label current municipal
ward context, not newly certified2026 legal precincts; other25 source wards
remain table-only. Do not loop failed old deployments.

**Previous accepted increment:** Maine partial locality activity under `f6a9e98`.
Both modes retain all 584 source regions: 480 mapped and 104 native / 48
reference areas held per mode, on the full 528-area 2024 contextual reference.
Complete immutable release `439851515` includes every source/reference/frame
decision, originals, identity inputs and offline code/results. All eight assets,
174 tests, 11,438 independent checks and two blocked exact replays pass.
Pages `42738234318`, guard `42738234642`, artifact `13727918651` pass:
**988,975,450 payload / 991,528,960 tar bytes**. All 27 checked production files,
both-mode desktop/mobile/all values and holds/stale-detail/retry, CT169,
providerall61/HI4/WV priority/all51 pass. All 436 old complete routes remain.
Do not repeat this completed review/build/package/release/acceptance.

**Previous native increment:** Connecticut town reports under `4d26889` (numerical
source `5e8e75b`) expose all 169 native VV counts / 1,150,127, with the separate
Total excluded from the map sum. Immutable release `439819338`, all seven
assets, 169 tests, 1,460 independent checks and two exact offline replays pass.
Pages `42735904153`, guard `42735903986`, artifact `13727556269` pass:
**988,726,858 payload / 991,283,200 tar bytes**. All 25 checked production files,
CT169 desktop/mobile/raw cells/retry, all61 provider frames, HI4/WV priority
and all51 navigation pass. All 436 old complete-download routes survive.
Town boundaries remain explicitly contextual 2024, not certified 2026 precincts.

**Previous accepted batch:** provider `5fc4f81` connects held activity in
38 states: 61 provider frames / 4,621 source-county counts, with two stronger
native West Virginia modes retaining priority. Complete immutable release
`439800051` includes all 102 frame decisions, 6,371 regional queries, 79 raw
originals and 63 qualified frames in 39 states; seven assets were anonymously
verified before main. ZIP: 52,460,406 bytes / 144 members. 71,197 independent
checks, two exact network-blocked reproductions, 165 tests and Astro/build pass.
Pages `42727767147`, guard `42727766817`, artifact `13723313458` pass:
**988,580,213 payload / 991,129,600 tar bytes**. All 23 checked production files,
all 61 desktop/mobile frames, native HI4/WV priority, source retry and all51
geographic interactions pass. All 436 old complete-download routes remain.
Do not repeat this completed collection review/package/release/build/acceptance.

**Previous accepted native increment:** Hawaii source `56c6252` connects the four native
election administrations, with Maui including Kalawao, not five invented
Census-county totals. Complete release `439767310` has sufficient original
reports, all nine geographic decisions, 496 unchanged unit records, full
original/grouped reference inputs and offline code/results. All six full assets,
160 tests, two exact blocked-network reproductions and actual desktop/mobile/
source-retry/all-51 interactions pass. Pages `42721367937`, guard `42721367517`,
artifact `13721431268`: **988,250,714 payload / 990,781,440 tar bytes**.
All 18 checked production files and all 436 earlier complete routes pass.
Do not repeat this completed acquisition/review/package/deployment/acceptance.

**Accepted native source:** Connecticut `5e8e75b` and complete immutable
release `439819338` connect 169 native town VV counts / **1,150,127**, with the
separate Total never added again. All eight native columns balance; 13 blank
PR counters, EV/mode/printed cells and source statuses survive. Native election
108 identifies November 3, 2026; both 52337/52338 payloads remain unchanged.
Full held **2024 contextual municipality** shapes are not certified 2026
boundaries, nine county totals or 776 precinct observations. All analysis rates,
denominators and generic cast/unique claims remain withheld; other mode fields
are not assigned inferred definitions. Complete 175,231-byte / 23-member ZIP,
all seven anonymous assets, 1,460 independent checks, two blocked exact replays,
169 tests/Astro/build/local desktop/mobile+all51 pass.
Original Pages `42731735479` built successfully, then both its first deployment
and one deployment-only retry timed out during `syncing_files`. The original
artifact `13725048820` remains; neither failed watcher downloaded it.
`deploy-pages@v5` explicitly clamps 1,800,000 to 600,000 milliseconds; do not
repeat the mistaken longer-window assumption. Workflow-only successor `4d26889`
corrects that value without changing numerical inputs, CT code or its release.
The fresh `ct-native-supported-timeout-production-acceptance-01` completed
successfully and was read. Exact native artifact/caps/production acceptance is
recorded above; do not duplicate its successful build, download or checks.

**Accepted source:** Maine `f6a9e98` is live; immutable release
`439851515` has all eight complete assets anonymously verified before activation.
The 665,845-byte / 19-member ZIP preserves every source/reference/frame decision,
all sufficient held originals and exact offline code/results. 11,438 checks,
two network-blocked reproductions, 174 tests/Astro/build/local desktop/mobile
both modes/stale-detail clearing/retry/CT169/all51 pass. ONE
`maine-production-acceptance-01` completed successfully and was read. Exact
native artifact/caps/production acceptance is recorded above; do not duplicate
the successful artifact download or browser checks.

Maine's two 584-region provider frames each have
480 one-to-one matches to full held 2024 municipality shapes: 441 already-
qualified historical identity links and 39 unambiguous Twp/Plt aliases. No
historical voting counts/rates are transferred. Lincoln/Rangeley/Unity/
Washington town identities are explicit; their ambiguous Plt/Twp counterparts
stay held. Each mode retains **104 native regions / 48 reference areas held**.
Native source-category parent totals reconcile. The immutable input builder
has run once; complete 1,168 native / 1,056 reference / two mode decisions and
four focused tests pass. Adapter/renderer/strict-reference edits now
pass 25 focused tests and Astro with zero errors/warnings; a dedicated browser
check and complete-package script now pass locally and offline; the source
and complete release are published. Actual production acceptance has passed;
continue the remaining county/precinct gaps. This separately labeled partial local
activity layer may use only proved matches, retaining all original records and
holds; do not aggregate into counties or invent full coverage/native election
IDs. No new geometry acquisition is needed for those held inputs.

Preserve native dates, category `votes` and collector-versus-native election
context. Activity is not full-election turnout, certified ballots or unique
people. Do not add early/mail modes, replace native positive/zero/partial
snapshots, allocate state totals or promote held jurisdictions. Explicit
Official never substitutes provider data. Actual production default county audit finds
only **AK/IL/MA/NH contest fallbacks**; Maine now has partial locality activity,
not inferred county totals;
eleven former contest-only states have uniform source-activity counts.
Pursue these remaining scope-specific gaps using held inputs first. This does
not complete nationwide native precinct coverage.

**Next held Alaska review:** complete native 2026 app-shape delta decoding
produces all 402 topology decisions without new acquisition or repairs.
81 paths are valid as OGC polygons without repairs; 321 retain source
self-intersection/topology holds. All map approvals remain false until native
ring/display semantics and election-vintage qualifications are independently
checked. Reuse the already-reconciled 523 reporting-unit counts, including
402 geographic, 120 pooled district and one federal-overseas unit. Do not
repair source paths, allocate pooled/federal counts, infer rates or substitute
locator repairs just to force a map.

**Accepted live:** website `cb79d84` connects West Virginia's separate county
modes and all 64 Colorado returned-and-processed counts. Pages `42717017978`,
guard `42717018339` and native artifact `13717918487` pass. Actual payload is
**988,185,251 / tar 990,709,760 bytes**. All 16 checked production files match
the artifact; desktop/mobile native values, Methods/source recovery and all
51 geographic interactions pass. All 436 earlier complete routes remain.
The deployment sync timeout is resolved. Do not repeat these successful
acquisitions, packages, builds, releases or acceptance checks for activity.

Colorado's already-held original workbook now supports **all 64 county
returned-and-processed counts**. Complete release `439743253` includes the
original, seven worksheets' cells, all three native mode frames, full 2026 county
reference, code and results. Its 1,023,255-byte / 16-member ZIP, six full assets,
612 source checks, 402 further checks, two blocked-network reproductions,
156 tests and desktop/mobile native-value checks pass. No county rates,
cast-ballot relabeling or precinct coverage is inferred. Do not reacquire this
source or publish another research-only proposal instead of finishing the view.

West Virginia's complete **220 county/mode decisions** are now published in
immutable release `439728452`, targeting website source `d0371e8`. It preserves
three independent county ballot snapshots (52 held), separate **55-county early
and 55-county returned** frames, and 55 download-only request records.
All six complete assets, original workbook cells, 687 independent checks, two
blocked-network reproductions, 152 tests and local desktop/mobile/all-51
interactions pass. All-method counts are never replaced with early/returned
counts, modes are never added, and all rates remain withheld. Native Pages and
actual-production acceptance passed in the combined successor above; do not
declare nationwide completion. The five newly
denied county results products and the statewide challenge
remain stopped. Reuse these originals and the full source package, not another
county crawl or a repeat acquisition.

Continue the remaining county gaps using held inputs first. Hawaii's
administration integration is complete above; do not restart it or a completed
historical-control family. Delaware's held candidate JSON contains no native
participation fields. Its separate 41-House-district native turnout query is
already published, but those counts are not allocated to the three counties.

Indiana's complete numerical/source package is now immutable at release
`439670388`: all 93 original statistics rows, 92 county decisions, 24 independent
follow-ups and 103 Monroe reporting units. It supports **75 county counts /
17 held** and **83 current-reference mapped units / 20 geometry holds**.
Every original zero, literal measure, separate clock/status conflict and the
unchanged partial state subtotal survive; no rates or candidate substitutions.
The 28,598,360-byte / 133-member full archive, all eight assets, 4,425 independent
checks and two exact blocked-network reproductions are verified. Website
`9377b8c` is **live and production-verified**: Pages `42703763791`, native artifact
`13712737717`, actual payload **988,132,436 / tar 990,658,560 bytes**. Exact
unqueried production files, desktop/mobile native values/source recovery and all
51 county/precinct interactions pass. All 436 old complete routes remain.
Do not repeat this successful acquisition, package, deployment or acceptance.
Continue the 16 contest-only states, Maine and within-state gaps. West Virginia's
declared general-results product reaches robot verification and is stopped;
follow independently published county originals, not another client or state
survey/candidate allocation. Its separate historical-results page lacks a
2026 general link, but the elections index declares the challenged product.

The navigation repair is live at website `9513311`: state/year/measure
selections are retained, absent data is explicit and failed sources can be
retried. Website `2694065` then replaced contest-count fallbacks with explicit
native ballot parents for all **44 Idaho and 53 North Dakota counties**.
Idaho has 43 reviewed source-registration fractions; Twin Falls stays held.
North Dakota's 53 rates and denominators stay held. All 1,344 earlier
reporting-unit rows and their precinct holds survive. Both states use
separately hash-verified **2026 Census county references**, not older precincts.

The complete 97-query download includes every selected/held result, sufficient
originals, geometry and offline code. Original-workbook/API checks, two exact
reproductions, 131 tests and actual production desktop/mobile/native-value and
51-jurisdiction interaction audits pass. Pages `42663520237`, native artifact
`13696510311`: actual payload **983,878,341** / tar **986,388,480** bytes.
All old links, short Methods and 436 complete-download routes are preserved.

**Still not nationwide observed turnout:** source county observations now cover
31 states plus D.C. (some only one or two counties), including Maryland's separate
Cards Cast measure, Indiana's mixed labels, Colorado's returned/processed counts
West Virginia's separate source modes and Hawaii's four native reporting
administrations, with separate RI/VT municipalities.
This is not 31-state complete voter/ballot coverage.
Sixteen states retain explicitly labelled
contest-count fallbacks and Maine has no county layer. Mapped precinct
participation remains partial in seven states
(ID, ND, MN, MI, NM, VA, IN) plus D.C.
Website `a218d82` now exposes the already-held **523 Alaska / 496 Hawaii**
source-unit observations as selectable/searchable counts, without pretending
held boundaries or rates exist. Pages `42666789732` succeeded; exact live
script/index, desktop/mobile source checks and all 51 navigation checks pass.
Website `23f0a33` additionally exposes **1,763 Arizona / 2,768 Arkansas /
432 Wyoming** complete native CSV records. All 4,963 records and 83 missing ballot
totals survive; missing counts are not zeros and all rates/maps remain held.
Pages `42670805978`, native artifact `13699406690`: actual **984,124,912 payload /
986,644,480 tar bytes**. Exact production script/index, all 5,982 source-unit IDs,
desktop/mobile missing/zero/deeplink/download/retry checks and all 51 geographic
selections pass. The current map integration, website `965fbc2`, connects D.C.'s already-reviewed
144 native precinct ballot/registration records and official-app reference,
with provisional-source fractions and explicit older-reference provenance.
It also exposes Virginia's 710 existing reference joins as counts only. All 710
mapped ballot values independently match the native `ballotsCast` field,
including 260 where the distinct `voterTurnout` field differs. The basis text
names the `voterTurnout` object, not a substituted count. Reuse the unchanged
source/map package; retain all 1,819 exclusions and withhold all rates.
Both maps are accepted on actual production: every native value, desktop/mobile
sidebar/retry and all-state navigation check passes. Pages `42675737057`
succeeded; native artifact `13701385628` has **984,130,264 payload /
986,644,480 tar bytes**, with the exact scripts/pointer, complete new inputs,
old downloads and short Methods preserved. This supersedes the earlier D.C.
executions that failed inside GitHub before building.

**Whole-state 2026 participation is the current priority, not another navigation
or registration-frame exercise.** Real default-page state clicks reproduce the
remaining gap: Texas/New York/Michigan previously showed county candidate counts,
not participation. Passing navigation tests or drawing polygons is not coverage.

Website `51f8010` is live and connects the complete 24-county-equivalent Maryland
**Cards Cast** report, explicitly not qualified cast ballots or unique voters.
Every rate/denominator stays withheld; all 25 native county/state records and the
full original PDF survive in its complete 633,225-byte download. It also includes
the preserved Bay/Isabella explicit ballot parents and unchanged 63 source units;
the other 81 Michigan counties remain missing. Both complete archives, 2026 county
references, exact offline reproductions, 139 focused/page/context tests, four build
tests, Astro checks, desktop/mobile source values/retries and all 51 geographic
selections pass on actual production. Pages `42687510890` succeeded; actual native
artifact `13706930410` has 987,714,304 payload /990,238,720 tar bytes. Scripts, both
complete archives, generated MD/MI APIs and all 436 old full routes match the
verified deployment. The generated JSON is byte-identical across platforms;
only gzip's platform byte differs locally. Both bounded integrations are accepted,
not nationwide completion. Do not reacquire or repackage successful sources.

The complete Ohio 88-report attempt returned88 exact-route403s and no PDFs/counts.
Ohio/New York statewide roots and Michigan's dashboard also returned403, while
South Carolina's declared general-results link reaches a verification challenge.
All remain stopped; no alternative-client/cache/mirror promotion. The source-access
ledger preserves every query without pretending metadata are a numerical release.
Texas's candidate-table "Ballots Cast" and New York's governor-vote proxy remain
excluded. Continue distinct permitted whole-state participation publications or
held originals, starting with the remaining large gaps, then test actual integration
and publication. Do not allocate surveys, candidate votes or district totals.

Alaska's encoded portal geometry still has unresolved topology; Delaware's
41 district observations cannot be apportioned to counties. Keep Texas
registration-frame research paused; do not substitute another research release
or a repeated completed source campaign for this live geographic integration.

**Latest priority: 2026, then an audit.** The new statewide Civic demographic
package is published: 671 supported model shares across all 50 survey states,
with complete source/disclosure holds and explicit D.C. absence. Its existing
2026 Demographics integration is live at `5005b2e`; all 36 production browser
configurations and the [post-integration audit](docs/AUDIT.md) pass. Models
remain separate from reported ballots. Resume genuinely unresolved observed
demographic, denominator and election-year geography evidence, not this
completed calculation, publication, interface or audit.
Older 2002 selection is paused; do not restart completed historical batches.

**Reported already-voted profiles completed:** new use of the held LVB
reduction gives 124 disclosure-qualified profiles across 49 source states
(46 overall / 78 age), with all 306 decisions and 612 stage cells retained.
Native LVB5 is an Already voted response, not an administratively verified
ballot. Other/unresolved combines future intentions, nonintentions and
unknowns, NOT nonvoters/staying home. Field period/calibration unqualified;
no common-date early-vote curve, pooled/national profile or model joint.
Old parent masks, n100/n30, legacy marginal-difference and age-complement
guards retain 182 holds, including one extra whole-age-profile hold.
Sixteen tests, 20,712 checks and two exact offline reproductions pass;
complete safe inputs/code/tests/query/results published without private
fine cells. Ohio's distinct primary-certification release and Iowa's
primary-results index returned403 and remain stopped; no cached count
or denied body used. Native28, age study, old 1,530 model-query bytes and
website unchanged; broader 49 independent administrative gaps remain open.

**New same-age registration-frame scenario completed:** already-held SC
65-Up Female/Male/Unknown-gender cells give a complete derived 1,045,477
registration units, not a printed age parent. The accepted public Civic
SC 65+ group has 553 cases and native model classes 518/35. Its own
propensity transported to that stock yields 1,028,954.96 participant /
16,522.04 nonparticipant SOURCE UNITS, not observed voters or staying home.
Boundary labels match; population/status/field-period/age-clock
exchangeability stays UNVALIDATED. The November 2 report label is not a
known cutoff/clock/timezone. All 255 state/age decisions include 254 holds;
other states lack selected age inputs here, not a claim of world absence.
No CA 66+ substitution, bin splitting, unknown recovery, under-65 complement,
statewide probability allocation or local estimates. Fifteen tests,
1,963 checks and two exact offline reproductions pass; complete sufficient
inputs/code/tests/queries/results published. All 1,530 existing model
queries/native28/website unchanged; broader 49 independent gaps remain open.

**Maryland general-election references completed; native28:** exact declared
workbooks give 4,293,322 ACTIVE and 283,680 INACTIVE registrations as of
October 18, 2026, kept separate. The distinct unofficial PDF reports 2,079,801
Cards Cast / 4,293,322 Eligible Voters, 48.44%, run November 8 at 7:44 p.m.,
timezone unspecified; actual title includes MIB2. These are not certified
unique voters/ballots or complete canvass. All 350 stock cells, 25 card
references and 66 accounting rows reconcile; same-agency products are not
independent population validation. No participation-by-party joint or
precinct records. One unvalidated statewide ACTIVE-frame transport adds
a scenario without fitting to cards; all 50 other states / 51 prior
dispositions / 33 scenarios remain exact. Current native28 has 51 state/D.C.
rows, 52 dispositions and 34 scenarios, NOT 34 states. Fourteen tests,
4,006 checks and two exact offline reproductions pass; complete sufficient
inputs/code/tests/queries/results published. The stopped October monthly
PDF was not retried; an older web preview was not a numerical input.
Existing CPS/2026 models/website unchanged; broader 49 independent gaps open.

**Four-election, every-state CPS histories published:** newly acquired
2018/2020 originals add 1,734 group snapshots, extending the complete
query to3,468 rows across2018/2020/2022/2024. All1,734 accepted2022/2024
registered queries/rates remain exact. The1,734 same-type comparison
decisions preserve three registered and one citizen missing-endpoint
holds; arithmetic is not harmonized population or causal change.
Older1018-character records lack PRSUPINT; native-9 is not invented
noninterview status, and the2018literal question-date placeholder stays.
Unknown registration/voting and sparse diagnostics survive. Fifteen
tests,550,090 checks and two exact offline reproductions pass; complete
sufficient inputs/codebooks/code/tests/queries/results are published
without raw respondent identifiers. Native27/2026 models/website unchanged;
broader independent2026 demographic/precinct/population gaps remain open.

**2026 retrospective-response classifications published:** separate
nonpartisan package reuses held Civic joints for77 supported tables
(33 recalled2022House /44 recalled2024President), not77states.
All102 state/contest decisions /408cell queries /204conditional-rate
queries include25holds. Other/unresolved prior responses retain explicit
nonvote AND unknown together, never classified as prior nonvoters.
Current-state/source weights do not certify prior residence/population,
observed2026turnout or new/returning voters. Existing100current-parent
checks remain exact; no source reduction/model campaign rerun.
Fifteen tests,4,652checks and two exact offline reproductions pass;
complete sufficient safe inputs/code/tests/queries/results are published.
NYHomeNoJS returned403 and is stopped; no cached count promoted.
Native27, existing model outputs and website unchanged; broader gaps open.

**Every-state CPS registration-supported groups published:** new
PES1/PES2 joint analysis covers all 1,734 state/year/group queries for
2022/2024, with 1,731 conditional estimates, three empty frames and383
sparse registered-case flags. Routed voters and explicit registration-yes
responses define the source frame, not independently validated registry
membership. Unknown registration stays outside it; voting unknowns within
it stay in the full denominator. All 1,734 prior citizen-frame totals
remain exact. Fifteen tests, 234,228 checks and two exact offline
reproductions pass; complete sufficient inputs/code/tests/queries/results
are published without respondent identifiers or private fine cells.
No administrative population, 2026 projection, local allocation or new
rate/map/view. Louisiana's facts/parish routes yield context/unresolved
host only; Nevada's news route is200/challenge, NOT403/statistical input.
Current native27, website and broader49 independent evidence gaps unchanged.

**Mississippi multiyear frames completed as a separate package:** new
October2022/2024 reports extend the held2026 frame to three dated ACTIVE
stocks and three registration-stock comparisons, not turnout/retention.
Two separate historical CPS rounded CVAP marginal-ratio scenarios have
unvalidated date/status/registry transport; complements do not identify
reported nonvoters or unknown responses. Existing2026 Civic units are
reused exactly, with all three cross-year model comparisons held.
All nine year/source decisions, 246 county rows / 492 counts / 246
percentages survive. Nineteen tests, 4,433 independent checks and two
exact offline reproductions pass; complete sufficient originals/public
inputs/code/tests/queries/results are published. Native27's51state
decisions/51dispositions/33scenarios and website remain unchanged.
No new local/group allocation or rate/map/view; broader gaps stay open.

**Mississippi active-register frame integrated conditionally:** version27
adds October's derived all-82-county sum of 1,888,362 ACTIVE registrations,
not a printed statewide parent or qualified November population.
One unvalidated dated/status-specific frame scenario uses full Civic
weights; conditional units are not observed people or staying home.
All 328 factual cells / 164 counts / 82 percentages are preserved.
Mixed CVAP vintages and three percentages above100 remain context, never
turnout, a model denominator or evidence of illegal voting.
Fourteen tests, 2,384 checks and two exact offline reproductions pass;
the complete original/input/code/test/query/result package is published.
All fifty other state rows / fifty controls / 32 scenarios survive;
now 51 dispositions / 33 scenarios, not33states. No new rate/map/view.
New Hampshire's homepage403 is stopped; Illinois's declared totals page
is200/application error, not403. Neither yields numerical evidence or
global absence. Broader independent demographic/precinct gaps remain open.

**Indiana primary-context register integrated conditionally:** version26
adds its explicit 4,713,746 Registered Voters from the 2026 PRIMARY report,
not November election-time population or an inferred registration date.
One separate scenario transports the general Civic propensity to that
primary stock under unvalidated cross-election/frame assumptions.
Conditional units are not observed people or staying home. Native primary
807,059 Total Voters / 553,110 Election Day / 253,949 Absentee are context
only, never general ballots, model validation/calibration or a matched
residual. All 92 counties / 665 cells / 372 counts / 186 source percentages
are retained; 97 equations and all rounding diagnostics pass. Raw percentage
binary lexemes are preserved; voter counts stay exact. Thirteen tests,
6,164 checks and two exact offline reproductions pass. All fifty other
state rows, 48 controls and 31 scenarios survive; now 50 dispositions /
32 scenarios, not 32 states. Complete original/inputs/code/tests/queries/
results are published; no new rate/map/website view. Illinois's two
HTTP200 navigation pages remain unqualified numerical discovery, not403/
paid-only/global absence; no purchase, personal voter file or guessed report.
Earlier source holds/releases/models and the provider-frame package survive.

**Reported demographic-frame arithmetic published:** the new provider
package covers all 408 state/mode/dimension decisions and 511 group/held
rows, with 135 source-native counts / 32 demographic views in 11 states.
Percentages use each demographic response's own total, not a population
or larger mode denominator. All Unknown/Undesignated/native-bin labels
and twelve zeros survive. Twelve parent-total discrepancies remain
explicit; no residual-to-unknown imputation. Matching dates/totals do not
validate equivalent frames. Provider404s for AL/DC/MA/NH are source-specific
holds, not zero voting. These are partial provider count compositions,
NOT group turnout, accepted/cast/unique-person certification, survey
projection or independent official validation. All 376 other scope
decisions remain held. Twelve tests, 13,997 checks and two exact offline
reproductions pass; complete sufficient source inputs/code/tests/queries/
results are published. Existing captured reductions were reused without
new acquisition or collector rerun. Native controls25, all survey models,
source403 holds and website remain unchanged; broader gaps stay open.

**D.C. native references integrated without survey projection:** version25
adds September 30 registrations and four separate voting-mode reports.
All 13 pages / 20 factual grids / 4,517 raw slots / 1,515 count slots
preserve 23 unknowns and seven printed zeros. Printed ward headers, not
page order, identify all eight wards / 144 registration precincts.
Merged detention cells do not shift dates; blank mail-report days are
not filled or treated as cutoffs. The 326 complete equations reconcile;
16 remain incomplete. Twelve tests, 31,661 checks and two exact offline
reproductions pass. No cross-mode generic cast/unique-person sum,
received-to-cast promotion, residence-ward rate or matched September
denominator. D.C.'s Civic sample stays absent: no projected model or
extra conditional scenario. The prior 185,086 ballot / 457,371 register
reference, all 51 state rows, 43 controls and 31 scenarios survive
byte-identically; now 48 dispositions / 31 scenarios, not 31 states.
Complete permitted factual inputs/code/tests/queries/results are published;
no new website view. Michigan's statistics index and Tennessee's election
index returned403 and are stopped without alternate clients/caches/mirrors
or cached counts. Broader independent group/precinct evidence gaps remain.

**Alabama monthly active/combined frames integrated separately:** version24
adds October's 3,390,357 active and 3,853,181 combined registrations,
not November inferred from the URL directory. Exact cutoff day/clock/
timezone remain unknown. The overlapping frames are never added;
462,824 inactive registrations do not establish nonparticipation or
ineligibility. All ten month sheets / 15,400 slots / 14,280 count slots
preserve 2,293 blanks and 666 formula caches without execution or zero
filling. Independent readers agree; 911 complete equations reconcile,
1,339 remain incomplete. Ten tests, 164,529 checks and two exact offline
reproductions pass. All 51 prior state rows, 41 controls and 29 scenarios
remain byte-identical, including Alabama's existing election denominator/
count/rate/scenario. Two new conditional statewide source-register frames
are unvalidated, not observed turnout or staying home; no local/group
allocation, linked ballot residual, rate/map/website approval. Now 43
dispositions / 31 scenarios, not 31 states. The complete original/input/
code/test/query/result package is published; prior releases/holds survive.
Broader independent demographic participation and precinct gaps remain open.

**Same-type historical model arithmetic delivered:** the new public AP
comparison package retains all 6,426 decisions and computes 505 supported
state/group/pair contrasts, each with two separate native weight views.
Pairs are 2018-to-2022 midterms and 2020-to-2024 presidential elections.
Only already-public supported endpoints and exact native code/label
matches enter the arithmetic. Full denominators/unknown model masses
are retained; sex/gender and race contrasts remain held.
Ten tests, 183,662 checks and two exact offline reproductions pass.
This is not observed turnout change, validated model/population
equivalence, a fixed cohort, individual switching or a causal estimate.
No original reduction or old public campaign was rerun.
Complete prior public inputs/queries/code/tests/results are downloadable;
current controls23 and website remain unchanged. New MO registration-index
and OH aggregate-portal403 routes are stopped, with actual byte/hash
receipts, no cached counts or individual voter downloads. The new
automatic snapshot parent is preserved; broader native evidence gaps
remain open.

**Minnesota registered-only snapshot integrated:** version23 adds
3,927,036 Registered Voters as of the native November 2 table caption,
excluding the separate 94,621 preregistrants aged16/17. The current
table is not assigned the older linked workbook dates. All 87 counties /
267 cells / 176 counts and both separate population totals are verified
by independent parsers. Ten tests, 1,351 checks and two exact offline
reproductions pass. Conditional registered-only units remain unvalidated,
not observed participation, legal eligibility or election-time population.
All fifty other state rows, 40 prior controls and 28 scenarios survive;
now 41 dispositions / 29 scenarios. Prior partial MN results stay held.
A distinct MT results-export page returned200 with a visible TEST banner:
unqualified, no test count selected or modeled. Its separate denied
registration-index route remains stopped. Complete factual inputs/code/
tests/queries are downloadable. No new website view, ballots/residual,
rates/maps, group/local allocation or population validation.

**Idaho dated register integrated separately:** version22 adds the
official 2026-11 Total 1,056,803. The actual published selector values
and CSV template were followed, not guessed. All three original views /
44 counties / 35 legislative / two congressional districts preserve
609 raw cells and 504 count slots; 102 equations reconcile.
Ten tests, 3,051 independent checks and two exact offline reproductions
pass. The index's November 2 update is not a qualified registry cutoff,
clock or active-only status. Conditional registry units remain unvalidated.
The primary 731,980 ballot count and registration disagreement are not
repaired; its primary denominator/rate remain null. Only separate-scenario
availability changes in the state query. All fifty other states, 39 prior
controls and 27 scenarios survive; now 40 dispositions / 28 scenarios.
Complete originals/inputs/code/tests/queries are downloadable. No new
website view, matched ballot/model residual, local/group allocation or
observed-staying-home/population claim. Broader gaps remain open.

**Oregon monthly register integrated separately:** version21 adds the
native 3,112,307 monthly Total, prepared November 3, not a qualified
registration cutoff or active-only status. All seven pages / 2,220
slots retain 44 observed zeros and 74 percentages; 298 equations
reconcile. Ten tests, 9,907 independent checks and two exact offline
reproductions pass. Conditional monthly-register units remain unvalidated,
not observed participation/staying home. Every prior state row is
byte-identical; 37 prior controls and 26 scenarios survive, with
39 dispositions / 27 scenarios now available.
The distinct returned-envelope report's formal-analysis warning is
respected: held context only, no model/calibration use or cast substitute.
Legacy fine-cell zero-filling is not reused. Full originals/new views/
sufficient inputs/code/tests/queries are downloadable. No new website
view, matched group rates, population validation or local allocation.
Broader independent participation and precinct gaps remain open.

**Historical state-group models extended:** the new AP/NORC package
provides 1,603 supported non-overall state/year/group cells across
2018/2020/2022/2024, each with two separately labelled weight views.
All 12,138 query decisions and sparse/source/disclosure holds remain.
Group views are supported in 45/44/40/46 states, not all groups everywhere.
Fourteen tests, 243,257 new independent checks and two exact blocked
offline reproductions pass; all 2,114 positive-cell partitions are checked
with synchronized weight-stage masks. The successful original native
reductions/verification were reused, not repeated.
These are source-weighted registered-frame models, not administrative
turnout or validated populations. Native categories, 2018 inference caveat,
2022 DE/WV and absent-RACETH5 holds, and D.C. absence remain explicit.
No class-case support or design interval is fabricated. Complete permitted
inputs/code/tests/queries/prior AP package are downloadable; no new
website view. Version20 controls and the broader independent administrative
participation/precinct gaps remain open.

**Further registration-source holds:** direct acquisition of Iowa's
separately declared November registration PDF and preliminary participation
release returned403, as did Wisconsin's statistics page, Massachusetts's
distinct modern statistics hub and Kentucky's registration index.
All five routes are stopped without alternate clients/caches/mirrors,
guessed files or promotion of web-parsed counts. The six-observation
machine ledger also preserves Iowa's separate legacy-index404.
Actual body sizes/hashes are recorded where available; Wisconsin's
unexposed body fields remain null. Native numerical inputs were not
acquired, so version20 controls/estimates/complete downloads are unchanged.
Pursue genuinely distinct permitted products or already-held numerical
evidence; do not loop through these routes.

**Nebraska filtered registry report integrated:** version20 adds its
explicit 1,265,022 Grand Total, not estimated VEP or legal-eligibility
certification. Native processed November 1 / printed November 2 clocks
are distinct, not independently qualified registration cutoffs or live
updates; timezone, active/inactive status and filter criteria remain
unknown. All 93 counties / 752 count slots preserve 126 blanks without
zero filling or shifted columns. Twelve tests, 5,018 independent checks
and two exact offline reproductions pass. All 102 accounting checks
are evaluated; 29 complete equations reconcile, 73 remain incomplete.
The complete query has 51 state/D.C. rows, 37 dispositions and 26
conditional scenarios; fifty unaffected states, 36 prior controls and
25 prior scenarios survive. Conditional filtered registry units are
not observed participation/staying home; no ballots/residual, population
validation, rate/map, local/group allocation or new website view.
Full original/sufficient inputs/code/tests/queries are downloadable.
Montana's distinct registration index returned 403 and is stopped;
Nevada remains iframe-only unqualified discovery, not an actual 403
or acquired native numerical input. Broader independent demographic
participation and precinct-coverage gaps remain open.

**South Carolina registration workbook integrated:** version19 adds the
explicit overall state parent 3,470,220. November 2 is the declared report
label, not an embedded registration cutoff/clock; status/timezone remain
unknown. All nine views / 46 counties per view / 14,121 cells / 6,768
registration slots and 945 missing count cells are preserved without
zero filling or complement recovery. Ten tests, 87,960 independent checks
and two exact offline reproductions pass. All 2,588 accounting equations
were evaluated; fully observed ones reconcile and incomplete ones remain
incomplete. The complete query has 51 state/D.C. rows, 36 dispositions
and 25 conditional scenarios; all fifty unaffected states, 24 prior
frames and 35 controls survive. Native demographic margins describe
registration stocks, not participating voters or CPS/Civic-equivalent
groups. No group/local probability allocation, observed staying-home
claim, native ballots/residual or new rate/map/website view.
Full original/sufficient inputs/code/tests/queries are downloadable.
Successful acquisition and frozen independent snapshot were reused.

**West Virginia preliminary source reference integrated:** version18 adds
the agency's 463,912 ballots cast / 1,210,385 registered / printed38.33%
from its November 6 release. Publication is not the count or registration
cutoff; clocks/timezone remain unknown. Counts were preliminary before
canvass, not complete/certified/generic turnout. Early cast and absentee
received stay nonadditive; historical percentages remain unmatched context.
Ten tests, 199 independent checks and two exact offline reproductions pass.
The complete query has 51 state/D.C. rows, 35 dispositions and 24 conditional
scenarios; all fifty unaffected states, 23 prior frames and 34 controls
survive. Native-minus-model is not validation or observed staying home.
All permitted factual numerical inputs/code/tests/queries are downloadable;
full page prose/app code/contact details stay outside the release.
No new rate/map/website view.

**Kansas dated workbook frame integrated:** version17 adds the native
October 1 Grand Total 2,027,520. All four worksheets / 105 counties /
169 districts / four repeated state parents survive; the repeated
geographic margins are counted once, not as four populations. All
2,645 cells and 1,946 accounting slots retain 299 blank/empty values,
without zero filling, missing-party complements or formula execution.
Date-only cells do not establish a midnight clock. Ten tests, 24,725
independent checks and two exact offline reproductions pass.
The complete query has 51 state/D.C. rows, 34 control dispositions and
23 conditional frames; all fifty unaffected states, 22 prior frames
and 33 controls are preserved. Party affiliation is not votes;
active/inactive status and population transport remain unqualified.
No native ballots/residual, local allocation or new rate/map/website view.
Full original workbook, sufficient inputs, code, tests and queries are
downloadable. November/December index entries were unlinked, not guessed.

**Oklahoma/Pennsylvania source-registration frames integrated:** version16
adds two explicit native parents: Oklahoma 2,455,735, declared as of
November 1 with a separate printed clock / absent timezone; Pennsylvania
9,052,695, labelled for the November 3 general election but with registration
cutoff/time/timezone unknown. Do not turn the election label into a registry
date. All 144 counties, two state parents and 730 native count cells reconcile.
Ten tests, 3,021 independent checks and two exact offline reproductions pass.
The complete 51-state/D.C. query has 33 dispositions and 22 conditional
frames; all 49 unaffected state rows, twenty prior frames and 31 controls
survive. Party affiliation remains registration accounting, not votes;
active/inactive status and population transport are unqualified. Ballots/
residual, local allocation and new rate/map/website view remain withheld.
Both full originals, sufficient inputs, code, tests and numerical queries
are downloadable. Earlier access holds and releases remain intact.

**New Jersey dated total-registration frame integrated:** version15 adds
the native total 6,747,375 dated November 3, 2026. All 21 counties / 242
count cells and original party codes are preserved as registration
accounting, not votes. Active/inactive status and exact clock are
unspecified; election-day dating is not independent cohort/population
validation. Ten tests, 507 independent checks and two exact offline
reproductions pass. The complete query has 51 state/D.C. rows, 31 control
dispositions and twenty conditional frames; all fifty unaffected states,
nineteen prior frames and thirty controls survive. State ballots/residual
remain null, with no local allocation or new rate/map/website view.
New York's November workbook and Maryland's October PDF returned 403
on direct acquisition; both routes are stopped and no cached counts used.
Full successful native inputs, receipts, code, tests and queries are downloadable.

**Connecticut dated active-register frame integrated:** version14 adds the
native October 19 active-registration parent 2,255,397, not election-time
population or a replacement for partial results registrations. All 169 towns,
2,550 count cells, source literals and native arithmetic are preserved.
Separate results versions and thirteen zero-registration / fourteen
zero-voted towns remain held; zeros are not zero populations.
Eleven tests, 4,651 independent checks and two exact offline reproductions pass.
The complete 51-state/D.C. query now has thirty control dispositions and
nineteen conditional scenarios; all fifty unaffected states, eighteen prior
frames and 29 prior controls survive. Native statewide ballots/residual,
population validation, local/group allocation and new rate/map approval
remain withheld. Full native inputs, code, tests and numerical queries are
downloadable; no website view changed.

**Following registration-source screening:** Texas's November page and
Maine's separately advertised March active/inactive workbooks returned 403;
all three routes are stopped, without another client/cache/mirror or
search-snippet denominator. Louisiana's declared statewide link contains an
unresolved environment hostname and returned 502; no target was guessed.
These are source-access/link holds, not evidence that the underlying
populations are zero or that no data exist. Four observations are recorded
in the source ledger; complete version14 analyses/downloads are unchanged.

**Utah dated active-register frame integrated:** immutable `438718321`
adds the native November 2 active parent, not an election-time denominator
or a replacement for county-report registrations. Version13 has 51 state/D.C.
rows, 29 source-control disposition records and eighteen conditional frames.
Native arithmetic discrepancies, all ten state / 228 county affiliation rows,
29 county participation rows and all prior counting/denominator holds remain.
Eight tests, 197 independent checks and two exact offline reproductions pass;
all 50 unaffected states, seventeen prior frames and 28 prior controls survive.
Native statewide ballots/residual remain null; no party-vote inference,
population validation, new state rate/map or website view. Raw operational/
personnel worksheets remain excluded; complete permitted numerical inputs
and queries are downloadable.

**South Dakota derived complete-county frame integrated:** immutable
`438706606` adds a clearly labeled 66-county registration aggregate, not a
native statewide parent. Version12 has 51 state/D.C. rows, 28 source-control
disposition records and seventeen conditional frames. Each county is counted
once; repeated vote-center registrations, unqualified `CurrentDateTime`,
all 671 original unit bytes and 596 available / 75 held rate decisions remain
unchanged. Eight tests, 1,280 independent checks and two exact offline
reproductions pass; all 50 unaffected states, sixteen prior frames and 27
prior controls survive. Native statewide ballots/residual remain null; no
native parent, population validation, new state rate/map or website view.
This supersedes the older screening-only note without promoting a county
sum to a native statewide source field.

**Alaska native federal frame integrated:** immutable `438694717` adds
explicit federal ballots/registration parents, not candidate totals or
generalized statewide turnout. Version11 has 51 state/D.C. rows, 27
source-control disposition records and sixteen conditional frames. Federal
overseas/governor scope differences, uncertified 400/403 reporting, missing
timezone and all 523 reporting-unit bytes/quality holds remain intact.
Eight tests, 615 independent checks and two exact offline reproductions pass;
all 50 unaffected states, fifteen prior frames and 26 prior controls survive.
Generic cast-ballot/rate/map/final-RCV approval remains withheld. The native
contrast is not observed staying home or population validation. No new
acquisition, old candidate/CSV/geometry reduction or website view.

**Virginia registration-only frame integrated:** immutable `438683276`
adds the explicit native state registration parent, corroborated across all
133 localities without replacing the state ballot zero. Version10 has 51
state/D.C. rows, 26 source-control disposition records and fifteen conditional
frames; no observed statewide ballot reference is added. Every locality
clock/status, all 2,529 prior precinct rows and the 69 locality/House residual
scopes remain intact. Seven tests, 1,612 independent checks and two exact
offline reproductions pass; all 50 unaffected states, fourteen prior frames
and 25 prior controls survive. State ballots/turnout/residual stay analytically
null. No acquisition, old candidate/precinct/geometry reduction, population
validation or website view. Continue genuinely missing supported frames.

**Arizona registration-only frame integrated:** immutable `438672280`
adds the explicit native state registration parent without repairing its
inconsistent active/inactive components or statewide ballot zero. Version09
has 51 state/D.C. rows, 25 source-control disposition records and fourteen
conditional frames; the new record is not an observed statewide ballot
reference. All 15 county / 1,763 precinct rows and the missing virtual
observation remain intact. Seven tests, 295 independent checks and two exact
offline reproductions pass; all 50 unaffected states, thirteen prior frames
and 24 prior controls survive. Native state ballots/turnout/residual stay
analytically null. No new acquisition, old candidate/precinct reduction,
population validation or website view. Continue genuinely missing supported
frames, not this completed integration.

**Washington registration-only frame integrated:** immutable `438661685`
adds the held explicit state `totalVoters` parent, not a repaired state ballot
count. Version08 has 51 state/D.C. rows, 24 source-control disposition records
and thirteen conditional frames; the new record is registration-only, not an
observed statewide ballot reference. Literal state zero, missing analytic
state ballots/residual, 39 county / 9,588 unit rows and King's unallocated
ballots remain intact. Seven tests, 419 independent checks and two exact
offline reproductions pass; all 50 unaffected state rows, twelve prior frames
and 23 prior controls survive. Both denied routes remain stopped. No new
acquisition, completed native-unit reduction, population validation or website
view. Continue genuinely missing source frames, not this completed increment.

**Arkansas explicit parent frame integrated:** immutable `438650649` adds
the held native state/75-county registration parents, not a reconstruction
of incomplete precinct registrations. Version07 has all 51 state/D.C. rows,
23 controls and twelve conditional frames. All 2,768 leaf rows and their
1,108 missing registrations / 82 missing ballots remain unchanged.
Six tests, 579 independent checks and two exact offline reproductions pass;
all 50 unaffected states, eleven prior frames and 22 prior controls survive.
Unofficial partial reporting, register-definition and rate/map holds remain;
no observed demographic turnout, local allocation or website view is claimed.
The Washington index and distinct results product returned403 and remain
stopped. Continue other supported statewide sources, not retries or substitutes.

**Delaware held statewide frame integrated:** immutable `438634132` adds the
previously published separate ALL/41-district source to complete version06:
51 state/D.C. rows, 22 controls and eleven conditional frames. Missing turnout
clock/timezone, unapproved native rate/map/completion flags and separate
candidate context remain unchanged. Six tests, 327 independent checks and two
exact offline reproductions pass; all 50 unaffected state rows and ten prior
frames are preserved. No new source acquisition, candidate reconstruction,
population validation or website view. Do not repeat this completed increment.

**New Mexico native state reference complete:** immutable `438620865` adds
33 counties and 2,204 source precincts, independently reconciled and retained
in the complete 51-state query. Version05 now has 21 native controls and ten
conditional frames. All 50 unaffected states and nine previous scenarios are
preserved. Native sign-in/Votes Cast semantics, unofficial status, distinct
October30 registration snapshot and zero-denominator hold remain explicit.
Six tests, 9,018 independent checks and two exact offline reproductions pass.
No new website view or demographic/local survey allocation is claimed. Continue
genuinely missing state/group frames; do not repeat this completed acquisition,
reduction, reproduction or release.

**California registration corroboration complete:** immutable `438609932`
retains all 58 county/age/preregistration vectors and preserves every prior
state row and nine scenarios byte-identically. It adds dated native evidence,
not another estimate or a group turnout rate. Preregistration overlap and
incompatible age bins remain explicit; do not repeat the completed acquisition
or numerical/reproduction checks. Georgia's three new direct403 holds remain
stopped. Continue distinct supported whole-state sources, not alternate clients
or inferred denominators.

**Every state is the required scope, not Florida-only additions.** A complete
2022/2024 demographic package is now published for all 50 states plus D.C.
The state-selectable integration is live and exact-production verified at
`ca883d0`: choose Demographics, 2022 or 2024, then Geography.
Nationwide 2026 demographic and precinct coverage remains unfinished;
no state survey estimate is allocated to local geography.

**Methods/documentation increment complete:** the website's short estimation
overview and organized GitHub guides are published and exact-production verified.
Accepted website revision is `96d7257`; the earlier `5e11695` repair remains a
preserved baseline. Resume genuinely unresolved statewide/group denominator,
return-reconciliation and election-year geography evidence below. Do not repeat
the completed Methods build/publication or prior successful research packages.
The broader project remains open; the single 15-minute continuation stays active.

| Priority / task | Status | Required result |
|---|---|---|
| Utah dated native active-register parent | Complete numerical integration and fully verified research publication | Release `438718321`: native Totalactive1784255 dated11/02/2026, NOT election-timeR or county-report denominator substitute. ConditionalDATED ACTIVE1133689.62/650565.38 units under unvalidated exchangeability. Inactive314971/combinedtotal2099225 arithmeticdiscrepancy1 retained, not repaired. All10state/228county affiliationrows are registrationaccounting, notpartyvotes;29priorcounty participationbytes/26reports/19counted+18paired/sixholds+fourmissing/oldDavis/Wayne/backend-zero holds preserved. Version13: 51 rows, 29 source records, eighteen frames. Eighttests/197 independentchecks/two blocked exact reproductions pass; all50 unaffectedstates/seventeen priorframes/28controls intact. Native statewide ballots/residualNULL; no acquisition, old PDF/OCR/workbook reduction, denominator substitution, rate/map/population approval or website view. |
| South Dakota derived complete-county frame | Complete numerical integration and fully verified research publication | Release `438706606`: derived sum628563 from66 unique native countyVoters parents, NOT native statewide field; conditional296578.40/331984.60 units under unvalidated exchangeability. CountycalcVoterTurnout310298 diagnosticonly; native statewide ballots/residualNULL. Repeated registrations at12vote-center counties ignored; exact native IDs/literal suffixes matched. CurrentDateTime semantics/timezone unqualified, not updateclock. Original671unitgzipbytes/596available+75held rate decisions/duplicates preserved. Version12: 51 rows, 28 source records, seventeen frames. Eighttests/1280 independentchecks/two blocked exact reproductions pass; all50 unaffected states/sixteen priorframes/27controls intact. No native statewide parent, acquisition, old candidate/workbook/HTML reduction, new state rate/map/population approval or website view. |
| Held Alaska native federal parent | Complete numerical integration and fully verified research publication | Release `438694717`: b215906 native federal ballots/v605433 registered, not t213009 candidate selections. Conditional291012.21/314420.79 units and native-minus -75106.21 remain unvalidated source contrasts. Governor215776/604611 differs exactly federaloverseas130/822; no scopeblend. Native400/403 reporting, uncertified, timezoneabsent, schemaformat2024 not electionyear2026. All523 originalunit gzipbytes/402geo/120pooled/1federal and221accounting/63ballots>registration holds preserved. Version11: 51 rows, 27 disposition records, sixteen frames. Eighttests/615 independentchecks/two blocked exact reproductions pass; all50 unaffected states/fifteen priorframes/26controls intact. Genericcast/rate/map/finalRCV/population approval stays withheld; no acquisition or old candidate/CSV/geometry reduction. |
| Held Virginia registration-only parent | Complete numerical integration and fully verified research publication | Release `438683276`: explicit state totalVoters6494441, conditional units3762883.24/2731557.76 under unvalidated exchangeability. All133 locality/registration totals and native active+inactive components agree; definitions remain unqualified. State ballotsCast0 retained raw, selected statewide ballots/turnout/native-minus-model NULL; locality3593781 not substituted. All133 clocks/statuses and2529 priorprecinct rows preserved; precinct2798626 partial, all69 locality/House residual scopes unallocated. Version10: 51 rows, 26 disposition records, fifteen frames. Seven tests/1612 independent checks/two blocked exact reproductions pass; all50 unaffected states/fourteen prior frames/25 controls survive. No acquisition, old candidate/precinct/geometry reduction, rate/map/population approval or website view. |
| Held Arizona registration-only parent | Complete numerical integration and fully verified research publication | Release `438672280`: explicit state totalVoters4374827, conditional units2195821.90/2179005.10 under unvalidated exchangeability. Active/inactive components remain inconsistent; registration totals never repaired. State ballotsCast0 retained raw, selected statewide ballots/turnout/native-minus-model NULL; county2248900 not substituted. All15county/1763precinct CSV bytes and missing Mohave virtual observation intact. Version09: 51 rows, 25 disposition records, fourteen frames; no observed statewide ballot reference added. Seven tests/295 independent checks/two blocked exact reproductions pass; all50 unaffected states/thirteen prior frames/24 controls survive. No acquisition, old candidate/precinct reduction, rate/map/population approval or website view. |
| Held Washington registration-only parent | Complete numerical integration and fully verified research publication | Release `438661685`: explicit state totalVoters5170951, conditional units3431936.67/1739014.33 under unvalidated exchangeability. State ballotsCast0 retained raw, selected statewide ballots/turnout/native-minus-model NULL; county2266746 never substitutes. All39county/9588unit CSV bytes and King601199 unallocated ballots preserved. Version08: 51 rows, 24 disposition records, thirteen frames; one register-only record and no observed statewide ballot reference added. Seven tests/419 independent checks/two blocked exact reproductions pass; all50 unaffected states/twelve prior frames/23 controls survive. No new acquisition, old unit reduction, rate/map/population approval or website view. |
| Held Arkansas state/county parent frame | Complete numerical integration and fully verified research publication | Release `438650649`: explicit 1856404 registeredVoters / 893026 totalBallotsCast, all 75 county parents and unchanged 2768 precinct records. Version07: 51 state/D.C. rows, 23 controls, twelve conditional frames. Native v173 UTC clock and unofficial partial reporting retained; missing leaf fields never imputed. Conditional units are not observed staying home or validated populations. Six tests, 579 independent checks and two blocked exact reproductions pass; all 50 unaffected state rows, eleven prior frames and 22 prior controls preserved. No new acquisition, candidate reduction, rate/map approval or website view. |
| Held Delaware statewide register frame | Complete numerical integration and fully verified research publication | Release `438634132`: separate384862 BallotsCast/810407 RegVoters and all41 House districts, complete51-state query/22controls/11frames. Conditional397682.55/412724.45 units preserve unvalidated source-register exchangeability; no observed staying-home claim. Clock/timezone absent, native approvalsfalse, no countyallocation or candidateclock substitution. Six tests/327 independent checks/two blocked exact reproductions pass; all50 unaffectedstates/ten priorframes/21controls preserved. Existing native/candidate/survey verification reused, notrerun. |
| New Mexico native2026 participation | Complete numerical package; fully verified research publication | Release `438620865`: all 33county/2204precinct native counts, registered denominator1469718, nativeparticipants731209/49.75%; full51-state query,21controls/ten scenarios. Conditional units765694.90/704023.10 retain unvalidated exchangeability. The separate1462993 October30 register never repairs the election denominator; zeroR has no analyticrate. All50 unaffected rows/nine prior scenarios preserved; six tests/9018 independent checks/two blocked exact reproductions pass. No new websiteview, generic cast-ballot relabeling or cohort/population certification. |
| Native California 2026 register corroboration | Published and fully verified; estimates unchanged | Release `438609932`: all eight originals, 58 counties/separate totals, native age and overlapping preregistration frames; complete 51-state query. Six tests, 2,256 independent checks and two exact offline reproductions pass the 24-member ZIP. The 23,273,590 count matches the existing CA denominator; all nine scenarios remain byte-identical. No population/age transport, group turnout or new website view. Broader native evidence gaps remain. |
| 2026 statewide demographic models | Complete package, live interface and requested audit verified | Immutable `438581821`: 671 models / all 1,530 state/group decisions, 50 source states and explicit D.C. absence. Five tests, 28,496 independent checks and two exact offline reproductions pass. Website `5005b2e`, Pages `42534719520` and actual artifact `13638962850` pass all 36 production configurations; all 1,734 historical values and 436 complete routes survive. The post-integration audit adds 9,092 checks of exact fractions, held statistics, positive-cell complements and complete archives. No new source/runtime defect found; the legacy landing-checker baseline was corrected without runtime changes. Observed demographic turnout, population frames and nationwide precinct participation remain unresolved. Do not repeat this completed increment. |
| Every-state demographic participation | Complete historical package and live interface verified | Release `438552376`: all 51 jurisdictions in both 2022/2024; 1,734 state/year/group queries, 1,733 positive-source estimates and one absent Idaho group, all 11,906 source decisions, 5,202 nonresponse scenarios and 6,120 partitions. Seven full assets, 582,345 independent checks, six focused tests and two exact offline reproductions verify the 26,243,365-byte ZIP. Website `ca883d0` / Pages `42530121113` / native artifact `13637596097` passes all 30 production configurations and strict content/tar limits (981,301,627 / 983,808,000 bytes), preserving all old links, IDs, 436 complete routes and 106-word Methods. State filters retain national histories, native categories, full unknowns, sparse diagnostics and missing-not-zero. Do not rerun this completed increment; nationwide 2026 demographic/precinct evidence remains unresolved. |
| Extend statewide native registration frames: Florida | Published numerical package; complete reproducible code included | Version 04 / release `438515810` adds one Florida whole-state conditional scenario and a separate native participant/model comparison. Full query: 51 states/D.C., 20 controls, 14 selected references, nine scenarios; all 50 unaffected rows, 19 prior controls and eight scenarios identical. Native TOTAL 8,335,497 / 13,704,495; conditional model units 7,475,648.38 / 6,228,846.62 under unvalidated register exchangeability. Source clocks null, statewide flags blank, 60 provisional / 64 overseas county holds preserved; generic cast fields remain null for Florida. All nine full assets verified; 21 tests, 4,165 independent checks and two byte-identical offline reproductions pass the 23-member / 20,157,249-byte ZIP. No new source acquisition, demographic/local allocation, observed staying-home or website view. Broader denominator/geography gaps remain; do not repeat this completed numerical/publication work. |
| Short website Methods overview | Complete; exact-production verified | Live `96d7257`, Pages `42517487539`, artifact `13632291877`. A 106-word estimation overview links directly to GitHub methods; archive hidden by default. All 24 production modes, 51 targeted Node tests, four build tests and credential checks pass. Actual downloaded artifact content 981,248,921 / tar 983,756,800 bytes; all 3,107 old links, 263 IDs, 436 complete relocations and pinned data preserved. Governing `methods-overview-production-acceptance-01.json`. No new estimates or sources. |
| Organized GitHub methods | Complete; published and remotely verified | Concise README and current METHODOLOGY, separate data/reproduction guides, indexed source ledger, preserved package notes and original protocol; initial revision `4546524`. All 64 documentation links/anchors, reader/test names and 11 complete immutable download assets verified. Methods explain actual estimators and conditional assumptions; proposed/failed models stay explicit. Both old local HEADs/indices/unrelated files preserved. No need to repeat this documentation reorganization. |
| User-reported website navigation and missing-detail repair | Complete and exact-production verified | Live revision `5e11695`, Pages `42502356194`, artifact `13625184708`. Per-tab selections persist; Precincts uses loaded multistate coverage and retains NC specialization; missing participation detail exposes separate county candidate counts; Methods is grouped. All seven tab/failure/no-JS configurations, three fallback configurations, existing survey/landing checks, 62 outline checks and exact 9,718 TX / 4,105 MN precinct-value checks pass. All old links, IDs, full downloads and data remain. Do not repeat this completed repair; resume the held EAC historical controls below. |
| 1. Download Pushbuild national CSV snapshot | Acquired and byte-verified | Complete pinned archive and all 40 state CSVs held; proceed to candidate/count/geography controls. File presence is not county coverage. |
| 2. Acquire all declared Senate race files | Acquired | All 70 race responses plus national index, original comparison CSV and receipts held. No more duplicate acquisition is needed for this snapshot. |
| 3. Reconcile exact 2026 returns | Six identifier joins qualified and published; count/round gaps remain | All 34,492 native rows and original fields remain. The six missing county IDs now have corroborated reference IDs in separate columns, retaining native blanks. Of 23 additional named pairs, 22 counts agree and one difference remains with clocks. Original 7,165 equal/215 different cross-checks remain a separate baseline, not silently replaced. Four RI gaps resolve to an explicit 755-vote Overseas/Federal unit, not allocation. Of 234 civic candidate controls, 229 reconcile, four AK noncounty controls are held, and the ME 882-write-in gap remains. |
| 4. Build the actual 2024-to-2026 House panel | Exact source-count join computed, independently verified and published | Complete 3,152-county/5,192-fragment query, including all 2,639 positive pairs and 2,228 known-screen passes. Preserve all exclusions; same district labels do not establish matched boundaries. Next qualify remaining source/control and boundary exceptions and use the exact contest context alongside actual participation controls, not as measured turnout. |
| 5. Finish five-wave survey numerical outputs | Computed, selected packages published, Civic/AP views live and verified | Civic plus AP 2018/2020/2022/2024 tables exist. AP native verification covers 532,866 source and 12,024 aggregate rows, with 132,196 checks. Its selected public package has 602 rows and all 710 broad-query decisions, eight tests, 29,172 cached-selection/rate checks and byte-identical offline reproduction under two seeds. The historical view is live; every one of the 602 rows passed production checks. Preserve the 2018 qualifier, 2022 DE/WV holds and absent 2022 RACETH5. Do not repeat completed reductions or publication campaigns. |
| 6. Reconstruct the margin-change components | Civic computed and independently verified | Both 2024-President-to-modeled-2026-House and 2022-House-to-modeled-2026-House have switching, modeled nonparticipation, no-prior-contest-vote entry, other, unresolved and denominator components. All 714 separate demographic partitions reconcile. Do not call these original-coalition population or causal persuasion estimates. |
| 7. Tie returns and participation controls to estimates | Both held-source expansion increments verified and published | All 51 state/D.C. rows, 19 native observations, 13 selected state references and eight conditional registration-frame scenarios are persistent. VT and RI add scenarios after native-frame review; ID remains ballot-only and DC has no Civic sample. RI's declared parent registration is 794,266, not a repair of Federal-unit zero registration; its parent ballot zero is not statewide zero. MN remains partial, WY registration null, and HI's six-ballot discrepancy retained. AL/HI/NC/OR/RI have cast-ballot measure comparisons; CA/CO/VT retain other native numerator meanings. Sixteen tests, 1,953 new independent checks and two byte-identical offline reproductions passed, preserving the previous six scenarios and all 15 controls. Next extend supported historical matches and genuinely new whole-state controls, not these completed reductions. |
| 8. Integrate and verify supported estimates | Existing estimates preserved through verified UI repair | Latest accepted main `5e11695`, Pages `42502356194`, attempt 1, fresh artifact `13625184708`: uploaded/deployed identity and actual 981,247,039-byte payload/983,756,800-byte tar pass. All 3,103 prior links, 260 IDs and previous full assets remain; Methods and multistate Precincts are usable, with no added script URLs. Source-matched original survey views remain intact. Four intact archived snapshot relocations free space; all 432 previous full-download receipts remain in the new 436-file manifest. Governing receipt: `website-repair-production-acceptance-01.json`; earlier registration acceptance remains preserved. |
| 9. Close statewide historical/2026 holes | Direct Wyoming statewide reference published and live in version 02; broader coverage ongoing | Complete 255 state/year query, 434 study/weight comparisons, 18 selected references (15 qualified cast and three other measures), 16 conditional rows, 11 comparisons and 18 mode rows. The complete 25-observation ledger retains the original held Wyoming unit aggregate and Natrona +2 conflict, while separately selecting the explicit primary state PDF/workbook total 198,198. No R or geography is inferred. Ten historical/26 combined tests, 1,973 new independent checks and two byte-identical offline reproductions passed; all unaffected and modeled outputs remain unchanged. All 19 production browser modes pass for the updated source-selection view, with every old complete download retained. Do not repeat this completed increment; broader group denominators, histories and geography remain ongoing. |
| 10. Add additional source-supported precinct detail | Secondary to national/state work | Reuse existing Minnesota/Hawaii/Wyoming originals first; get missing whole-state releases/layouts rather than restarting county-by-county research. Local leads below are useful additions, not the critical path. |
| 11. Qualify remaining statewide registration frames | Wyoming's two declared reports and three supported scenarios published and live; broader frames ongoing | Complete 360 native county/state records, 105 accounting rows, 24 snapshot changes, two source comparisons, three separate AP/Civic whole-state conditional frames and 681 full survey dispositions are in immutable release `438053365`. Seven tests, 4,885 independent checks and two exact offline reproductions pass all 20 members/642,261-byte ZIP. Registers 297,639 (2022) / 281,219 (2026) do not fill election-time denominators; active/inactive and EDR inclusion are undeclared here. Native parties are accounting, not behavior. No county/precinct survey allocation. The folded view now passes all 24 production modes and four native direct-link configurations. Do not repeat this completed acquisition/reduction/publisher/build; continue genuinely missing state/group denominators. |
| 12. Extend historical controls with held EAC inputs | Complete, independently verified and published | Immutable `participation-eac-state-controls-20261108-01`, release `438401507`: complete 561 state/year grid, 15 native/held observations, ten selected references / nine qualified source-defined participation references, six Alaska AP frames, all 602 survey decisions and ten adjacent snapshot comparisons. Eleven original A-table registration joins match exact identities and frozen values. Ten focused tests, 11,326 independent checks and two blocked-network byte-identical reproductions pass all 21 members / 192,220,123-byte ZIP. All nine authenticated-draft and anonymous-public full assets match. Earlier Alaska rows, Maine UOCAVA-only, NH/RI unproved labels and Alaska 2024 highest-office proxy remain held; no harmonization, statewide unit summation or local survey allocation. Do not repeat this completed parse/reduction/reproduction/release or the huge workbook scan. No new website view is claimed. |
| 13. Extend historical demographic registration/participation frames | Held CPS increment computed, independently verified and published | Complete immutable CPS release `438418451`: all 28 originals; 3,203 native group-count rows (2000-2024), 2,573 percentage frames (31 elections, 1964-2024), 4,540 full workbook-row decisions, 3,792 nonresponse assignments, 2,407 same-election-type comparisons and all 602 AP frame decisions. All ten full assets match authenticated-draft and anonymous-public bytes. Nine tests, 221,990 independent checks and two byte-identical blocked-network reproductions pass all 43 members / 1,289,064-byte ZIP. Native margins, zero/N, merged unknowns and age/race/citizenship/education breaks remain. No population-scaled AP counts, observed staying home, local allocation or new website view. Do not rerun completed reductions or publication; extend genuinely missing native group/geographic frame evidence and independent source comparisons. |
| 14. Extend native historical state registration frames | Computed, independently verified and published | Immutable CPS state release `438432114`: all four original presidential/congressional voting/registration workbooks, 5,202 native cells, 2,754 complete state/year/population pairs (1972-2024), all 2,503 preserved voter observations, 2,550 same-election-type snapshots, 768 separate AP state diagnostics and all 1,204 query/frame decisions. Seven tests, 80,133 independent checks and two byte-identical blocked-network reproductions pass all 19 members / 368,608-byte ZIP. All nine full assets verified anonymously. Native early largest-state coverage, 153 absent citizen columns, unavailable N and pre-1996 citizenship breaks remain. No percentages-as-registration-counts, administrative validation or local allocation. Do not repeat this completed reader/reproduction/publication; continue genuinely missing native statewide/group denominator and geographic evidence. No new website view claimed. |

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

AP's reviewed public package is versioned at
`data/ap-votecast-aggregates/20261108-01/`, with maintained
`scripts/ap_public_aggregates.py`. Its
[complete immutable AP download](https://github.com/hanshanley/margin_of_error/releases/tag/participation-ap-history-20261108-01)
contains 218 national and 384 whole-state overall rows. The 710 broad-query
dispositions retain 64 nonresponse/disclosure holds, 30 support holds,
10 absent-2022-RACETH5 queries and four DE/WV state holds. No private state
demographic cells or raw source records are exported. The support screen uses
total positive-weight cases (500 whole-state, 1,000 national), not a minimum
per modeled-outcome class, which the cached statistics do not contain.
It is not a precision or anonymity guarantee. All unknowns remain in the full
overall denominators. Native group labels, four separate weight frames and the
2018 47-state inference qualifier remain intact.

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

The [complete Senate identifier package](https://github.com/hanshanley/margin_of_error/releases/tag/participation-senate-identifiers-20261108-01)
now qualifies all six source-missing county reference joins: Minnesota's
Lac qui Parle `27073`, Lake of the Woods `27077` and McLeod `27085`;
Montana's Lewis and Clark `30049`; Oklahoma's Le Flore `40079`; and
South Dakota's Oglala Lakota `46102`. This is a separate `resolved_fips` field,
not an invented native declaration. Original identifier/eligibility fields,
all 34,492 native rows and their votes/parties/clocks remain intact.
The 956,205-byte, 12-member ZIP includes all sufficient aggregate inputs,
complete queries, code and tests. Six tests, 69,225 independent checks and
two blocked-network, byte-identical offline reproductions passed.
The remaining single additional count difference is not reconciled away;
Maine write-ins, round qualifications and earlier source-count exceptions remain.

The [expanded conditional state-control package](https://github.com/hanshanley/margin_of_error/releases/tag/participation-state-controls-20261108-03)
is a 20,124,248-byte, 20-member ZIP plus all six full query/summary supplements.
Maintained `scripts/participation_controls.py` uses verified public Civic
aggregates, the frozen nationwide snapshot `20261108T023946Z`, the eight reviewed
2026 observations, UF initial estimates, exact state House context and the
already-held qualified Hawaii/Wyoming/Minnesota/Vermont/Idaho/Rhode Island/D.C.
source versions.
The eight `R*p`/`R*(1-p)` scenarios (AL/CA/CO/HI/NC/OR/RI/VT) explicitly assume
exchangeability of each state's survey propensity to that particular native
registered denominator. This is not validated; weight target/calibration and
field period remain unqualified. Source-defined, active, active-and-inactive,
eligible/pre-registered and native-undefined registration frames are not
harmonized. No independent outcome or original-coalition validation is claimed.
The source-weighted model's nonvoters are not administratively observed people
staying home; eligibility/death/migration stay null. Georgia's unqualified
registration total and North Dakota's unsupplied eligible denominator remain
null, not derived from UF VEP or a printed percentage.

Hawaii's declared statewide summary supplies 365,897 ballots and 853,399
registrations. Its 496 native units sum to 365,903 ballots; the six-ballot
difference, zero registrations and all precinct rate holds remain unrepaired.
Repeated statewide registration values across contests are never added.
Wyoming's 191,688 separate ballots reconcile across all 23 counties and 432
precincts; no registered denominator is supplied, and the Washakie candidate
category conflict remains. Minnesota's 4,105 native rows include only 2,490
reported flags and 15 ballot-mode discrepancies. Its 1,224,405 ballot sum and
3,986,420 registration-unit sum remain explicitly partial, not statewide
turnout or a state survey allocation target. No blocked endpoint or completed
font recovery was retried. The archive retains all sufficient public aggregate
inputs and original sources without acquisition session headers.

The next four-state increment retains all 247 Vermont municipalities, 986
Idaho units, 40 Rhode Island localities and 144 D.C. precincts. Vermont's
506,512 registrations support a conditional scenario, but its source-labeled
311,009 "Votes Cast" remain distinct from qualified cast ballots; all six
municipal rate holds and the 311,429 House accounting total remain.
Rhode Island's native parent `totalVoters` is explicitly 794,266 and equals
the sum of all locality registration fields. Use that parent denominator,
not inferred registration for its Federal unit (756 ballots, zero native
registration). All 39 municipalities plus that separate unit supply 364,082
ballots; the native parent ballot zero is not statewide zero. Its clock
differs from the older 755-vote Senate snapshot. Idaho's 731,980 separate
ballots cover 44 counties; Twin Falls registration (41,878 workbook vs 42,990
API), seven House/ballot-report differences and pooled-unit holds remain.
No state registration denominator is adopted. D.C.'s independently reconciled
185,086 ballots and 457,371 registrations do not create a Civic sample.

All seven version-03 assets were fully verified before and after immutable
publication. Sixteen tests and 1,953 new independent checks passed, including
preservation of the preceding six scenarios, 47 unaffected state rows and all
15 preceding controls. Two network/DNS/external-command blocked reproductions
matched every member and the complete ZIP. The initial and MN/HI/WY versions
remain immutable, with their earlier verification proofs intact. The new
outputs are published research downloads; no new website view, build or
deployment is claimed. Continue matched historical ballot/registration
controls from already-held sources alongside earlier-year demographic data;
the cumulative CES access hold is not a reason to stop the other work.

The [complete historical participation package](https://github.com/hanshanley/margin_of_error/releases/tag/participation-historical-controls-20261108-02)
is public and fully byte-verified, with maintained
`scripts/historical_participation_controls.py`. Hawaii historical native
ballots/registrations are 398,657/756,751 (2018), 579,784/832,466 (2020),
419,363/861,358 (2022) and 522,236/860,868 (2024). These reconcile separate
summaries and PDFs; registration definitions and voting-mode labels are not
silently harmonized. Wyoming's 198,198 native 2022 workbook sum remains held:
Natrona precinct/statewide 22,955 versus printed county 22,957. No registered
denominator or approved cast-ballot change is inferred from that held
aggregate. All 255 state/year
combinations remain in the query, so these selected histories do not imply
nationwide administrative coverage. AP and Civic remain separate source-
weighted model constructs, not a harmonized panel. The existing current
estimates are preserved. The compact administrative-history context is now
live and exact-production verified in the existing folded research section.
The completed source-resolution increment selects a **separate** Wyoming 2022
statewide reference: its original statewide ballot PDF and native summary
workbook both print 198,198, and their 23 county values match the native
precinct sums. The two-ballot Natrona county-print conflict and original held
aggregate stay intact; no registration or boundary approval is inferred.
The direct state observation is now selected in complete immutable version 02,
with both observations and every selection disposition in the 25-row ledger.
The updated context is live and exact-production verified, retaining all
first-version downloads rather than replacing them. Do not rerun this
successful build, publisher or acceptance campaign. The distinct 1978-2026
statistics package is also complete and published, but its pre-election
registration counts do not resolve missing election-time denominators.
Continue the genuinely missing, declared registration reports and supported
whole-state historical/group controls instead.

The accepted Pages tar has only 12,800 bytes of headroom under the strict
1,000,000,000-byte cap. A later automatic research snapshot has legitimately
advanced the underlying source repository; it was preserved in the House
source-only publication rather than reset. The next website increment must
measure its actual full build against current source context, keep large
complete downloads external and preserve every old route. The accepted Civic
artifact is not a size guarantee for a future build. The current website
workflow explicitly pins research source `792e3d`; the later automatic research
snapshot does not automatically change those staged website inputs. Preserve
that verified pin rather than changing it just because research main advanced.

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
| CES cumulative DOI `10.7910/DVN/II2DB6` | Native metadata request returned HTTP 403 on November 8, 2026 at 03:54:39 UTC; exact route stopped. No dataset/guide acquired and no alternate-client/cache/mirror bypass. Qualification awaits permitted source access or supplied originals. Continue using already held CES common/panel inputs and distinct historical sources for their supported years. |
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
