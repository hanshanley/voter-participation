# NORC source predictor-block ablation — repaired final-02

This metadata-only repair preserves every original numeric score and all original artifacts. It performs **no source refit**, creates no new scenario, and changes no default.

## Required erratum

The original protocol SHA-256 `8eecc164…1cc89` is retained as forensic evidence, but its declared `frozen_at` value is impossible: the file was modified at approximately 01:06:55 local while claiming 01:36. The original `rule_frozen_before_native_fits=true` claim is withdrawn. Local filesystem ordering is not independent time certification.

The comparison and arithmetic gate are therefore classified as **exploratory, post hoc, and based on already-seen source outcomes**, not externally preregistered or verified prefit-frozen.

## Correct source scope

- Historical AP analysis is a common **48-state** AP2022→AP2024 source transfer. DE/WV are excluded from both training and scoring; DC is absent. It is not all-state historical validation.
- CHEP contains observations from 50 states in one pooled respondent holdout. Those states are qualified only for pooled source-response analysis. State-inference qualification is not established by the held codebook evidence; no state scores are published.

## Correct execution accounting

- 10 multinomial logistic estimator fits.
- 2 training-weighted marginal baseline calculations.
- 12 total evaluations.

The small AP age/education differences—log loss `0.738564877355 → 0.735829569640`, Brier `0.357106096317 → 0.356447395408`—have no uncertainty analysis or new independent historical episode. AP uses one prior while CHEP uses two, so these are thematic rather than identical specifications. The arithmetic comparison is against `prior_only`, not the accepted full rich model. No scientific promotion or generalization claim is made. Sex/RUCC retains its mixed result: slightly better log loss and worse Brier.

## Aggregate replay

This standard-library replay does not refit private cases:

```sh
PYTHONHASHSEED=101 python3 -S -W error src/offline_replay.py \
  --facts facts/coarse-facts.json \
  --output /fresh/output
```

The harness monkeypatches and probes selected Python socket, DNS, and subprocess APIs. This is **not** an operating-system sandbox or proof of OS-level network/process denial. The replay requires no external command.

## Optional private refit

Observed fitting environment:

```text
Python 3.9.6
NumPy 2.0.2
scikit-learn 1.6.1
SciPy 1.13.1
threadpoolctl 3.6.0
```

With users' own exact qualified originals:

```sh
PYTHONHASHSEED=17 python3 -W error forensic-fit/fit_source_predictor_blocks.py \
  --ap2022 /private/AP2022.zip \
  --ap2024 /private/AP2024.zip \
  --chep2026 /private/civichealth_datafile.csv \
  --protocol forensic/original-protocol.json \
  --output /fresh/private-fit

python3 -S -W error src/apply_metadata_errata.py \
  --original-facts /fresh/private-fit/facts/coarse-facts.json \
  --erratum ERRATUM.json \
  --output /fresh/private-fit/facts/coarse-facts-repaired.json
```

The public aggregate replay cannot reproduce private source fits.

## Tests

From an extracted SDK with the observed optional fit dependencies:

```sh
python3 -W error -m unittest discover -s tests -v
```

Standard-library-only repaired-fact tests:

```sh
python3 -S -W error -m unittest tests.test_repaired_public -v
```
