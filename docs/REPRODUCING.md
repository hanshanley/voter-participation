# Reproduce a saved analysis

[Overview](../README.md) | [Methods](../METHODOLOGY.md) |
[Choose a package](DATA.md) | [Source notes](../SOURCES.md)

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
