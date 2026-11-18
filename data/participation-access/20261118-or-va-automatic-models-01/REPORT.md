# Accepted Oregon evidence and Virginia automatic models

The existing hourly pipeline now supports **13 House states / 117 state-variant
frames**, up from **12 / 108**. Formerly qualified frozen states decrease
**21 -> 20**. States: AR, DE, GA, HI, MN, NM, PA, RI, SD, TN, VA, VT, WY.
All nine existing Virginia variants consume compatible official revisions
without respondent refitting or repeated race-by-race assistant approval.

## What changed numerically

Virginia endpoints: D **2,105,772 -> 2,156,783**,
R **1,422,580 -> 1,436,340**, O **58,819 -> 61,053**.
Signed revisions: D +51,011, R +13,760, O +2,234.
These are candidate selections, not ballots, unique participants or observed behavior.
The full reference point and every variant are retained in the complete numerical
outputs; switching and nonparticipation remain assumption-dependent reconstructions.

The selected hosted collection refreshed Oregon's six contests/20 literal candidates
and Virginia's existing state-plus-133-locality source, from which all 11 federal
contests/47 candidates are derived and reconciled. The 470 national contests were
reused, not recollected. Formal-name/FEC rules were reviewed against retained evidence;
FEC registration alone never establishes general-election ballot presence.
No provider and official counts are added together.

Oregon explicitly warns that write-in results are not reported on this site.
Its automatically refreshed candidate evidence is useful but incomplete for that
purpose: exhaustive write-in/provider-equivalence/model/participation flags stay
false. It does not become an automatic conditional-model state.

Virginia uses its own complete official frame and native clocks. Every candidate,
generic write-in and minor-party count remains inspectable. Official failure,
inventory change or clock rollback preserves the last-good official outputs.
Virginia and Rhode Island cannot overwrite national accepted candidate/control
seeds; Hawaii's separately compatible seed-update behavior is preserved.

## Actual delivery and validation

Research `b3729bf217f4f2c6ee80f746feb111761a4af178`; workflow-only consumer `cd4618a8e00c908909024296c2b1732d2fe13fc1`.
Source run **44404611606**; data-only runtime **44409300973**,
version `2462d069f7c7be3912d019bcddcb9b8330de29bd9e451ec03338f9f3493e6c8b`. Actual hosted unchanged run
**44410571469** preserves the data/runtime and starts zero Pages builds.
All **22 source outputs** and **171 analytical outputs** match full public
bodies and reproduce literally offline on CPython 3.12 with zero requests.
The analysis reproduction also blocks external operations.

Controlled offline D+7, D-13 and one generic write-in's 1,021 -> 0 revision
propagate through all nine variants. Outage, incompatible inventory and
own-clock rollback retain last-good numerics and clocks. The offline runner
no-op fixture is separate from the actual hosted unchanged acceptance.
The completed numerical scenarios were reused after a replay-parent plumbing
repair; they were not falsely claimed as newly rerun.

Actual production desktop/mobile checks verify **288 exact Virginia model-map
values** across nine variants, eight metrics and both unit conventions.
All 11 district decisions agree with exports. Four actual screenshots were
physically reviewed. No source, data, DOM or style override was used.

## Coverage and remaining dependencies

All **435 districts** remain accessible; **259** comparisons qualify, with
176 held. **32 House states** and **28 Senate reader/export comparisons**
remain qualified. Two Colorado split-block comparisons support 261 scientifically,
but their compatible reader is prepared, **not deployed**. This batch requests
no Pages deployment and does not change effective district boundaries.
145 live holds concern changed block membership, 29 concern election/party/round
compatibility, and two are that deployment dependency.

Participation remains **4,857 compatible rate frames / 23 jurisdictions /
eight statewide frames**, with **zero new participation observation IDs** here.
Candidate returns cannot fill missing ballots or demographic denominators.

The 20 frozen formerly qualified states are AZ, CO, CT, IA, ID, IN, KS, MD, MI,
MO, MT, ND, NE, NH, NY, OH, OR, SC, UT and WV. Complete minor/write-in source
universes remain unresolved; identity and Arizona party-coverage restrictions
overlap. CA/NC have separate changed-party scientific restrictions.
Utah's retained provider has distinct named and generic 71-vote rows; equal
counts do not establish duplication. Official named-write-in data alone cannot
justify deleting the unmatched generic row. Empirical Senate respondent
questions/weights/history, Maine final-round/write-in evidence and matched
local/group participation denominators remain separate external/scientific
dependencies. This is not universal coverage or causal identification.

## Complete downloads

[Complete analytical ZIP](https://github.com/hanshanley/margin_of_error/releases/download/automatic-participation-2462d069f7c7be3912d019bcddcb9b8330de29bd9e451ec03338f9f3493e6c8b/complete-analysis.zip): **308,904,215 bytes**;
SHA256 `d9d1dbbfbe6c28b53d779a7d4db4c1d1aa3609706a698310362eb684b8ce1d53`.
Includes the full nested source packet, actual preceding rolling seed, complete
original science, reviewed identities/categories, geographic evidence, safe
aggregate priors, all numerical queries, code and tests.

[Complete source-results ZIP](https://raw.githubusercontent.com/hanshanley/voter-participation/a3ea2382e8a1935351bd5875fe28a67ba3098322/snapshots/620198a29e1bf2a48ff7c26f5ca3c59fce1472dc7d4b3d56993d122bf655b4f7/complete-results.zip):
**61,918,274 bytes**; SHA256 `a215aac9ed52290fbeb160bbc707ec067a353f0da06c17b218e32a08e121a437`.
Earlier complete downloads and immutable versions remain intact.

## Exact commands

Selected collection and publication, from the research checkout:

```sh
python3.12 -m scripts.results_intake refresh-selected --registry data/results-intake/registry.json --work-dir /tmp/election-intake --sources OR-official-house-candidates,VA-registered-1657a8451bae522c
python3.12 -m scripts.results_intake publish --work-dir /tmp/election-intake
```

Normal complete collection uses `collect` with the same registry/work directory.
The existing hourly workflow runs this pipeline without an assistant.

Analytical refresh with the reviewed engine and the existing website checkout:

```sh
PYTHONPATH=/path/to/research-source python3.12 -m scripts.automatic_runtime --repository /path/to/website --work-dir /tmp/participation-runtime
```

From a fresh extraction of the complete analytical ZIP:

```sh
python3.12 code/reproduce.py --replay-package . --output reproduced
```

From a separate extraction of the nested complete source-results ZIP:

```sh
python3.12 code/reproduce.py replay --package . --output reproduced
```

[Full acceptance](acceptance.json);
[desktop model](va-model-1440.png), [mobile model](va-model-390.png);
[desktop districts](va-districts-1440.png), [mobile districts](va-districts-390.png).
