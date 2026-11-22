# Water-only boundary screen

This audit starts from the complete comparison and Census transfer tables
in the `house-comparison-candidate-dae35928caf0` release. It covers the
117 advertised House districts whose sole remaining comparison hold is a
change in whole-block membership. FL-03 and FL-06 are not in the audit:
the candidate already verifies their water-only transfers separately.

The script reconciles each target's complete transferred-block roster to
the counts in the boundary review. It checks a bounded, deterministic
subset of those blocks in the Census 2020 TIGERweb layer. One nonwater
record rules out a water-only exception. If some blocks remain unchecked
and no nonwater record has been found, the result stays incomplete. Even
an exhaustive water finding does not automatically qualify a comparison.
The screen does not use 2020 population to infer 2024 votes.

In this snapshot, all 117 targets have at least one confirmed nonwater
block. The package includes all 307 checked records, each district's
decision, the three input query tables, and five original Census responses
with request URLs and checksums.

## Reproduce offline

With CPython 3.12, from the extracted package:

```sh
env -u PYTHONPATH python3.12 scripts/house_water_screen.py inputs reproduced
diff -r outputs reproduced/outputs
```

For a new accepted source packet, pass its complete ZIP as the first
argument and add `--collect`. Acquire only permitted source responses;
request failures halt collection instead of filling missing evidence.
