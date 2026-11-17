# Separately versioned partial Senate scenarios

The `participation.senate_legacy_partial_scenarios.v1` extension retains all
26 original fitted Senate decisions and the complete original scientific
archive. It does not update, relabel or replace the strict legacy models.
It adds no empirical Senate respondent model.

The initial reviewed bridge supports Alabama's regular Class II Senate seat,
2020 general election to the reported 2026 general election. Candidate identity,
seat, stage, round, full native facts, source identity and revision clocks are
checked on every automatic analytical refresh. A changed candidate inventory or
incompatible comparison is held, not automatically approved by a matching name
or matching major-party totals. The other 25 original decisions remain explicit
holds with their missing evidence recorded in
`data/results-intake/senate-legacy/review.json`.

## What is conditioned, and what is not observed

The reviewed 2020 endpoint contains Democratic 920,478, Republican 1,392,076 and
3,891 scattered/write-in votes. The accepted current report contains Democratic
759,321 and Republican 917,338. Current unreported Other/write-ins are **unknown**,
not observed zero. The bridge conditions only the current D/R counts and keeps
current Other and nonparticipation model-assumed.

The prior is the original disclosed President/House synthetic association
transported to Senate. It is not a fitted Senate question, an observed linked
history, total turnout or an estimate allocated to counties or demographic groups.
The common frame and persistence assumptions remain substantive limitations.

For the retained report, the D-minus-R margin change is +10.968435 percentage
points. The reference scenario attributes +4.666098 to switching, +0.425563 to
modeled nonparticipation, +5.773590 to entry and +0.103184 to Other-choice
transitions. These are conditional accounting components, not identified
individual behavior or observed staying home. Nine persistence/frame assumption
combinations are exported; their ranges are not confidence intervals.

## Automatic updates and failure behavior

The existing hourly source collector remains unchanged. The analytical producer
loads the reviewed evidence and the actual preceding runtime's output NEXT seed.
It reconditions compatible changed counts without private respondent fitting.
It preserves last-good scenarios and their own native model clocks on a failed or
incompatible update. Saved last-good native evidence is revalidated and the model
regenerated before reuse; a rechecksummed but altered checkpoint is rejected.
An identical input, processing fingerprint and dataset version exits before
compilation, publication or website building.

The optional consumer uses the same checksum-bound runtime pointer as existing
count/model readers. An absent optional descriptor preserves the archived view;
corruption leaves an explicit unavailable state with retry. Current partial
scenarios appear in a separate detail table, not as replacements for the archived
map. Reader source preparation is not a Pages deployment.

## Complete downloads and offline reproduction

Each complete analytical archive contains the full original predecessor,
reviewed native evidence, all 26 decisions, both endpoints, all nine scenarios,
all 144 synthetic transition cells, code, tests and checksums. The current
extension's CSV and JSON exports are under `queries/model-queries/senate/`;
read the packaged inventory rather than assuming a fixed output count.

From a fresh extraction using the packaged CPython 3.12 numerical contract:

```sh
python3.12 code/reproduce.py --replay-package . --output reproduced
```

This replays the permitted retained aggregate inputs without publisher requests
or private respondent fitting. It does not claim to re-extract excluded publisher
documents. Collection and analytical-refresh commands remain the existing
`election-night.yml` and data-only `automatic-runtime.yml` workflows described in
[REPRODUCING.md](REPRODUCING.md).

## Remaining scientific prerequisites

Strict complete-universe updates require compatible Other/write-in inventories
and reviewed source precedence as well as seat/stage/candidate identity. A truly
empirical Senate extension additionally needs compatible Senate respondent
questions, weights, historical inputs, a source-justified model and validation.
House respondent models cannot simply be relabeled as Senate models. A supported
electoral swing does not by itself qualify either extension.
