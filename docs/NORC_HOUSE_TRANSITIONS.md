# NORC-informed demographic House transitions

This model estimates how switching, entry/return, modeled nonparticipation,
Other-party choice and unresolved answers can account for state House margin
changes. It is an assumption-dependent explanation, not identified voter histories
or a causal effect. Moving from R+4 to D+12 is a +16 margin-point change.

## What is learned

Regularized multinomial models use state effects and interactions of previous
choice with demographics. The fixed regularization is C=0.15; source weights are
rescaled by their mean only for regularization. Actual joint demographic records
are used privately, not products of separate demographic marginals or the earlier
synthetic statewide coupling.

The 113,020 CHEP2026 cases recall 2024 President and 2022 House, not 2024 House.
An explicit bridge is therefore trained on 136,435 AP/NORC2024 positive-state-weight
cases: current House response from President, actual recalled 2022 House, age,
education, native race/ethnicity and income. AP QVOTE2022S is a forced
counterfactual and is never consumed. Actual AP recalled House party codes are
reversed from CHEP. Source gender is not silently mapped to CHEP sex.

The current CHEP response model also uses source sex assigned at birth and native
urban/suburban/rural county context. Current House response and likely-voter
classification define the target, never predictors; respondent IDs and LVB are
excluded. D/R/Other/modeled nonparticipation/unresolved remain distinct (DRONU).
Disclosure-removed attributes become unknown, not recovered categories.

The latent House24 and current response probabilities are conditionally
independent given the included joint predictors before extra latent-affinity
sensitivity. Current residence and demographic membership are transported to the
baseline under assumptions. They are not fixed historical cohorts.

## Prediction checks, not fitted-endpoint validation

Respondent tests use state-stratified 20% holdouts without return targets.
The historical test trains only on AP2022 and tests untouched AP2024 source
responses, using poll-close state weights and compatible age/education fields.
It is not a matched panel, same-election-type test or administrative validation.

| Test | Log loss without demographics | With demographics | Brier without | With |
| --- | ---: | ---: | ---: | ---: |
| House24 baseline bridge | 0.22529648 | 0.22444465 | 0.09892045 | 0.09899595 |
| CHEP26 House response | 0.54790594 | 0.47895891 | 0.25959448 | 0.22950076 |
| Untouched AP2022-to2024 transfer | 0.74408945 | 0.74173593 | 0.36005163 | 0.35960468 |

Lower is better. The bridge Brier score is slightly worse with demographics;
historical transfer improves only modestly. Predicting source likely-voter classes
is not independently predicting completed voting.

A separate state prediction uses previous House counts and current total
candidate-vote volume, but not the current party split. Across 35 comparable
states its margin MAE is **5.98790598 points**. Texas projects R+5.2075 versus
held D+5.7080, a +10.9155-point error. Every state error is retained as model
error, never assigned to another behavioral component.

## Conditional reconstruction and exact demographic accounting

Thirty-five states have qualified held 2024/2026 same-office endpoints.
Fifteen retain source-only scenarios and unavailable observed comparisons.
D.C. has no CHEP sample. None receives an invented recorded baseline.

Common row/column multipliers constrain each state's synthetic prior to its
recorded D/R/Other endpoints; those same multipliers apply to each demographic
partition. This separate return conditioning is not source training or validation.
Frame size is source-anchored and assumed, not eligible population.

For A=D-R and V=D+R, each flow/group mechanism k contributes margin points:

```text
C(g,k) = 50*(1/V0 + 1/V1)*deltaA(g,k)
         - 50*(A0 + A1)/(V0*V1)*deltaV(g,k)
```

This exact symmetric identity assigns denominator effects inside each mechanism.
The five signed contributions sum to the change in normalized D/R margin.
Net participation is entry plus exit, not only exit. Retaining party contributes
zero change while having a nonzero modeled share. U is never pooled into N.

Age, race/ethnicity, education, source sex, income and county context each
separately partition their state. Different dimensions overlap and must not be
added. Native disclosure/complementary holds remain; an opaque synthetic
remainder completes each partition without publishing withheld source groups.

Three frame scales (0.8/1/1.2) and three latent affinities (0.5/1/2) give 360
assumption cases. There are 250 overall seed cases (2.5 million draws) and 1,500
alternate demographic-partition seed cases (15 million draws), not that many
distinct people. Monte Carlo variation is not source/design uncertainty, and
assumption envelopes are not confidence intervals.

## Interpretation and reproduction

For example, the central return-conditioned estimates give the following
sum-preserving, rounded contributions. These are fitted explanations of the
held comparisons, not independently established behavioral percentages.

| State | Total change | Switching | Net participation | Other | Unresolved |
| --- | ---: | ---: | ---: | ---: | ---: |
| Texas | +25.16 | +14.50 | +9.15 | +0.41 | +1.10 |
| Minnesota | +11.96 | +7.16 | +4.06 | +0.33 | +0.41 |

Units are D/R margin points. Unrounded counts determine the change, so subtracting
separately rounded displayed endpoint margins can differ by 0.01 point.

Modeled absence is not confirmed staying home or no ballot in any contest.
Entry/return is not proven first-ever voting. Eligibility, deaths and migration
are not separately identified. Changing candidate availability, age, residence,
weights, source frames and incomplete reporting can affect results. No state
model is allocated to counties or precincts.

The full scientific download contains permitted fitted synthetic priors, all eight
complete outputs, every state/group/flow/assumption/seed query, code, tests,
independent checks and the entire accepted return-source predecessor.
Public simulation reproduction is complete and standard-library-only:

```sh
python3 -Werror code/scripts/reproduce_norc_house_model.py \
  --package . --output /fresh/output/path
```

Python3.9 is the reference byte-reproduction toolchain. Two fresh network- and
external-command-blocked reproductions match all eight outputs; nine tests and
51,712 independent endpoint/rational-accounting/demographic checks pass.
Private model-training reproduction requires the original user-supplied local
survey files and disclosure policy. Raw respondents, identifiers and private fine
source cells are not published or uploaded to CI.
