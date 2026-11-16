# Reproduce a saved analysis

[Overview](../README.md) | [Methods](../METHODOLOGY.md) |
[Choose a package](DATA.md) | [Source notes](../SOURCES.md)

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
