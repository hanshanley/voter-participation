# Reproduce a saved analysis

## November 18 current collection and complete offline replay

[Complete current runbook](../data/participation-access/20261118-complete-automatic-products-02/REPORT.md#collection-and-analytical-refresh). Accepted immutable source pointer: `https://raw.githubusercontent.com/hanshanley/voter-participation/13799554103654952200909a14af770cea8d3d55/latest.json`. Omit results_pointer in the existing workflow for ordinary latest-source refresh. Analytical runtime is data-only; it does not deploy Pages.

Extract each full package into a separate fresh directory. Analytical/source replay uses CPython 3.12 for analysis and Python 3.9+ for the source packet. Use each package's runtime/dependency declarations, not a floating-point tolerance.

```sh
# Complete analytical packet: 171 outputs, no network/private refitting
python3.12 code/reproduce.py --replay-package . --output reproduced
# Complete selected source packet: 22 outputs
python3 code/reproduce.py replay --package . --output reproduced
# Separate complete display-geography packet, using its requirements.txt
python -m scripts.replay_house_district_map --inputs inputs --expected expected --output reproduced
python -m scripts.verify_house_district_map --inputs inputs --output reproduced
```

All commands were accepted against their actual packaged code. An unchanged geography replay preserves bytes/mtimes. These are selected-fact numerical replays, not fresh source acquisition or empirical validation of individual histories. **Earlier runbooks below are preserved version-specific history, including their older pointers, output counts and delivery labels.**

## Current collection, analytical refresh and offline reproduction

The existing hourly writers perform normal updates. Manual equivalents are:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation --ref main
gh workflow run automatic-runtime.yml --repo hanshanley/margin_of_error \
  --ref main -f results_pointer=https://raw.githubusercontent.com/hanshanley/voter-participation/54fbdd10b792ffd845c0a18387bd0ee27a15d414/latest.json
```

The pinned pointer reproduces this accepted source; omit results_pointer for the default latest-source refresh. The latter workflow publishes analytical data only, not Pages. Extract each complete package into its own fresh directory.

Complete source-package reproduction:

```sh
python3.12 code/reproduce.py replay --package . --output reproduced
```

Complete analytical-package reproduction (161 outputs, no network or private fitting):

```sh
python3.12 code/reproduce.py --replay-package . --output reproduced
```

[Complete analytical packet](https://github.com/hanshanley/margin_of_error/releases/download/automatic-participation-1364db054b24734bc2b8406eca039e8e3c002914a4ff3834eb76a7fc2a3e53de/complete-analysis.zip); [complete selected source](https://raw.githubusercontent.com/hanshanley/voter-participation/254c986e1e8035dbb879209946aa035d89cf53ad/snapshots/9aab983ff3fcf686677dba0bc02a327931830eb8a864d44eda5f9d3c38d5febd/complete-results.zip). Engine `331d48409b1c8dafd37b8c06d03d510d8dcfd442`; consumer source `bcf72930a3ee225284dbb788c95b6b4cd7a2c788`. Both AL and NM include nine transported-prior assumptions, not empirical Senate fits. Failed/incompatible updates retain last-good data and their own native clocks. The reader patch is tested against actual public data but is not deployed.

## Current Senate extension, collection and literal reproduction

Use the published engine and consumer commits recorded in the coverage/downloads record. The existing hourly collector remains the broad intake; this increment reuses its accepted immutable source rather than running it again.

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation --ref main
gh workflow run automatic-runtime.yml --repo hanshanley/margin_of_error \
  --ref main -f results_pointer=https://raw.githubusercontent.com/hanshanley/voter-participation/54fbdd10b792ffd845c0a18387bd0ee27a15d414/latest.json
```

The latter is analytical data-only publication, not Pages deployment. Download each complete archive into its own fresh directory. Source extraction:

```sh
python3.12 code/reproduce.py replay --package . --output reproduced
```

Analytical extraction (all 161 complete outputs, no network or private fitting):

```sh
python3.12 code/reproduce.py --replay-package . --output reproduced
```

[Complete analytical packet](https://github.com/hanshanley/margin_of_error/releases/download/automatic-participation-e7a8cddafaa79c3194f75aa3065f0b316f58aca8d2d2fd2737a98a3794f37eb0/complete-analysis.zip); [complete selected source](https://raw.githubusercontent.com/hanshanley/voter-participation/254c986e1e8035dbb879209946aa035d89cf53ad/snapshots/9aab983ff3fcf686677dba0bc02a327931830eb8a864d44eda5f9d3c38d5febd/complete-results.zip). Failed/incompatible updates preserve last-good outputs and their own source clocks. No source refit, changed precinct geography or inferred turnout is introduced.

## Current automatic collection and literal offline replay

From a checkout of the published research engine identified in the coverage record:

```sh
gh workflow run election-night.yml --repo hanshanley/voter-participation --ref main
gh workflow run election-night.yml --repo hanshanley/voter-participation \
  --ref main -f refresh_sources=NE-official-house-candidates
```

Selected refresh requires the existing accepted collector state; it does not reacquire all other sources. The normal hourly collector includes the new candidate product. To pin the analytical refresh to this accepted immutable source:

```sh
gh workflow run automatic-runtime.yml --repo hanshanley/margin_of_error \
  --ref main -f results_pointer=https://raw.githubusercontent.com/hanshanley/voter-participation/54fbdd10b792ffd845c0a18387bd0ee27a15d414/latest.json
```

This is a data-only analytical publication, not a Pages deployment. Download each complete archive into its own fresh directory. In the source extraction:

```sh
python3.12 code/reproduce.py replay --package . --output reproduced
```

In the separate analytical extraction:

```sh
python3.12 code/reproduce.py --replay-package . --output reproduced
```

These accepted commands reproduce all 22/153 complete outputs without publisher requests or private respondent fitting. Preserve the packaged interpreter contract, complete inputs and checksums; do not substitute a metadata-only package.

## November 16 reviewed automatic analytical handoff

Actual hosted source **43920096796**, data-only consumer **43933156698**, and identical-input no-op **43933995521** are accepted. **435 House / 35 Senate** races refresh through the existing hourly bulk system. Recorded qualification is **32 House states / 28 Senate contests**, versus 32/24; the unchanged deployed reader badges 25 Senate comparisons and retains explicit reader-limit explanations for FL/OH/GA. All 28 are qualified in full CSV/query exports.

**AR/TN/VT automatically recondition all nine accepted model variants** when compatible counts change; the delivered release numerically changes AR/TN. The final replay/display repair preserves all 450 already-published state/variant numerical results. A diagnosed missing per-family endpoint receipt is also repaired: the unchanged strict live loader now accepts the fresh conditional models instead of falling back to embedded older estimates. Unchanged rolling runs preserve the actual last numerical endpoint's receipt. A subsequent physical screenshot review exposed equal array-valued clocks being rejected by the sensitivity reader. The compact exports now use matching literal clock strings; all full scientific results and original clocks are unchanged. Fresh nine-variant ranges are verified in the unchanged live reader, not merely present in a manifest. The other 30 formerly qualified states remain explicitly dated frozen results, alongside all 17 original scientific holds. Every old candidate record remains. All 435 district comparisons remain raw/boundary-held; Senate models lack a reviewed seat/stage/source-to-prior bridge. Candidate totals supply no new turnout denominator. No respondent refit, Pages deployment or assistant continuation is used.

For example, the original ridge Tennessee model now uses D **896,349** / R **1,095,895**, rather than 903,874 / 1,088,370. Its same-office D-minus-R margin change moves **22.417948 to 21.662519 pp**; modeled switching moves **8.908411 to 8.620090 pp**, and modeled net participation **12.351412 to 11.923061 pp**. These are conditional model components, not observed individual behavior. Full-precision before/after counts and points for all nine variants are included in the coverage/download record.

[Full coverage and 15 complete exports](../data/participation-access/20261116-congressional-analytical-handoff-01/coverage-and-downloads.json), [hosted/offline acceptance](../data/participation-access/20261116-congressional-analytical-handoff-01/acceptance.json), and [production verification](../data/participation-access/20261116-congressional-analytical-handoff-01/production-acceptance.json).

In a fresh extraction of this complete runtime, run:

```sh
python3.12 code/reproduce.py --replay-package . --output reproduced
```

This exact published packet reproduces 147 complete outputs offline. Optional re-extraction of the included official historical originals uses `openpyxl>=3.1` and `pypdf==6.16.0`; ordinary replay uses included full compiled facts, without respondent fitting. Use the checksum-bound producer interpreter declared in `inputs/numerical-runtime.json`; a mismatched interpreter is refused before computation, not accepted with a numerical tolerance.

[Overview](../README.md) | [Methods](../METHODOLOGY.md) |
[Choose a package](DATA.md) | [Source notes](../SOURCES.md)

## Automatic House and Senate results

The [complete congressional/runtime download](DATA.md#automatic-house-and-senate-results)
includes the entire source packet, all previous-election comparison inputs and
seven new congressional CSV/query outputs alongside the preserved analytical
products. In a fresh extraction, run:

```sh
python3 code/reproduce.py --replay-package . --output reproduced
```

The first delivered congressional runtime reproduces **139 complete outputs**;
read the packaged inventory rather than assuming this count for future versions.
This reuses existing fitted public models and does not refit private respondents.
To reproduce its complete source package separately, extract that ZIP into a
different fresh directory and run:

```sh
python3 code/reproduce.py replay --package . --output reproduced
```

The source package reproduces **18 complete outputs**, including normalized
race/candidate results, coverage and full query facts. Neither command
reacquires publisher sources. Source timestamps, retained status and comparison
holds are reproduced, not replaced by the replay clock. The downloadable full
query inputs preserve Senate seats, special contests, stages and rounds.

## Integrated supported analytical release

Extract the complete automatic runtime archive into a fresh directory, then run:

```sh
python3 code/reproduce.py --replay-package . --output reproduced
```

The package includes the entire pinned source packet, actual preceding rolling
seed, reviewed eligibility/frozen public aggregates, engine and complete outputs.
Replay recomputes the additional `release/` CSV/query products as well as the
existing datasets and models. It does not repeat private survey fitting or
publisher-document acquisition. The coverage query lists the exact output
inventory; do not assume the previous 113-output count for this successor.
The source packet has its separate literal `code/reproduce.py replay` command.
An immutable `results_pointer` workflow input can pin acceptance without
following the independently advancing hourly latest pointer.

## Historical precinct qualification

Use the [complete historical ZIP](https://github.com/hanshanley/margin_of_error/releases/download/participation-historical-qualification-20261115-01/complete-analysis.zip) (898,920,880 bytes, SHA256 `c8fa6b5a915175f1d6f0b37df4b25e9627bb504788ed44ae8a1604a9cd268bfb`).

Extract the complete ZIP into a fresh directory, then run:

```sh
python3 -I -S code/reproduce.py --output reproduced
```

The standard-library replay verifies packaged pins and reproduces all 48 complete
outputs offline, including 255 scope decisions and 2,286 qualified fractions.
Its four process-local offline denial probes and zero requests were checked.
It does not repeat private survey fitting or excluded publisher-document extraction.
The complete 874,127,644-byte earlier source authority and six complete component
packets are embedded, not replaced with metadata. All previous downloads below
remain available.

The source compiler checks native measure/election/year/unit labels, safe integer bounds, duplicate pairs and compatible registration frames. Positive/negative/default-preservation integration is covered by 24 maintained coupled tests; the embedded portable suite has 22 tests. The website count/native/history contract passes 67 tests.

## Complete-package workflow

Download and unpack the relevant complete ZIP into a new directory. Read its
included reproduction instructions and source manifest, then run from that
directory. Keep the output path new: readers refuse to overwrite an existing
analysis. **Use saved inputs; do not reacquire a successfully captured source.**

For example, the historical CPS state package reproduces with Python's standard
library and no network requests:

```sh
python3 -m unittest discover -s tests -p test_cps_state_frames.py
python3 -m scripts.cps_state_frames --inputs inputs --output reproduced
```

The complete 1996 native-state packet has its own standard-library-only runner:

```sh
python3 -Werror code/scripts/reproduce_cps_1996_state_points.py --package . --output /fresh/path
```

It verifies every packaged member, runs eight focused tests and 76,557 independent
fixed-column/CSV checks, then reproduces all ten result/query files byte-for-byte
with network and external commands blocked. The complete accepted 1998 science
is a frozen input, not a request to repeat its acquisitions or reductions.

## Maintained analysis entry points

The table identifies the matching reader and focused test. Input flags and
directory names vary by package; use its included instructions or `--help`,
not one guessed command for every analysis.

| Analysis | Reader in `scripts/` | Test in `tests/` |
|---|---|---|
| CPS demographic frames | `cps_group_frames.py` | `test_cps_group_frames.py` |
| CPS state frames | `cps_state_frames.py` | `test_cps_state_frames.py` |
| 1996 native state participation/response frames | `cps_1996_state_points.py` | `test_cps_1996_state_points.py` |
| Alaska Senate native parents and accounting scopes | `ak_senate_controls.py` | `test_ak_senate_controls.py` |
| AP public aggregates | `ap_public_aggregates.py` | `test_ap_public_aggregates.py` |
| Current state controls | `participation_controls.py` | `test_participation_controls.py` |
| Historical administrative controls | `historical_participation_controls.py` | `test_historical_participation_controls.py` |
| EAC state controls | `eac_state_controls.py` | `test_eac_state_controls.py` |
| Wyoming statistics | `wyoming_participation_statistics.py` | `test_wyoming_participation_statistics.py` |
| Wyoming registration | `wyoming_registration_controls.py` | `test_wyoming_registration_controls.py` |
| House comparison | `house_panel.py` | `test_house_panel.py` |
| Senate identifiers | `senate_geography.py` | `test_senate_geography.py` |

The Civic public package's portable reconstruction and tests are included in
that ZIP. The private `scripts.civic_estimates` and `scripts.ap_votecast_estimates`
read supplied, hash-qualified respondent inputs and require a new private output
directory outside Git. Public reproductions do not require those private files.

## Historical explorer development

From the repository root, install the declared dependencies only if needed:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m scripts.build
.venv/bin/python -m pytest
```

The historical build uses the saved source cache. Source acquisition and
`scripts.restore` are separate operations; neither is needed to rerun a complete
analysis package. Do not retry a recorded denied route through a different client,
cache or mirror.

## Check the actual result

Compare complete output files and source hashes, not just row counts or summary
metadata. Keep missing/unmatched/held decisions, native zeros, source
disagreements and separate weight frames. Existing release notes record the
independent checks and offline byte-identical reproductions already performed;
rerun only what a changed analysis or unresolved issue requires.

Website staging, artifact-size verification and deployment are maintained in
the companion website's
[publishing runbook](https://github.com/hanshanley/margin_of_error/blob/main/PUBLISHING.md).
A successful research reproduction is not a new production deployment.
