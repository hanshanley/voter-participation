# NORC-informed demographic House transitions

This model estimates how switching, entry/return, modeled nonparticipation,
Other-party choice and unresolved answers can account for state House margin
changes. It is an assumption-dependent explanation, not identified voter histories
or a causal effect. Moving from R+4 to D+12 is a +16 margin-point change,
equivalent to +8 Democratic **two-party-share** points, not +16 share points.

## Historical same-office panel check: conditional source concordance

The new check uses the held 6,175-case CES 2020/2022/2024 retained panel's
post-election House items at both waves, not a presidential-history substitute.
Administrative participation and reported House choice are separate axes:
codes 1..6 are positive histories, 7 is explicit nonvote and absent histories
remain unknown even with a positive choice. Contest nonvote, reported election
nonvote and unknown choice remain distinct. No contradiction is repaired.
The guide does not directly qualify panel-native numeric candidate labels.
Shared-item codebook transport is a stated assumption at the source-classifier
boundary; candidate position is mapped through its literal party field, with
blank/NA/__NA__/-1 party unknown. 2024 slots 6..8/code 12 and House-preference
counterfactuals are not used.

The primary table requires positive administrative histories at both waves,
known D/R House reports at both waves and positive `commonpostweight_24`.
Earlier 2022 weights are private sensitivity frames, not 2024 validated-voter
weights. The three-wave retained panel was recruited among 2020 adults and omits
newly first-age-eligible 2022/2024 adults. Native postwave weights do not prove
retention/attrition correction. Matched-record states reflect current record
geography (2024 field as of August 2025), not established election-day residence
or verified moves.

For weighted selected 2x2 cells `w_DD,w_DR,w_RD,w_RR`, the reported gross
switching percentage is `100*(w_DR+w_RD)/(w_DD+w_DR+w_RD+w_RR)`.
Directional rates use the corresponding previous-choice row denominator.
They exclude current Other/unknown/nonparticipation and therefore are **not**
rates among all members of the previous coalition or signed margin contributions.

| Selected source frame | Raw selected cases | Weighted D-to-R | Weighted R-to-D | Weighted gross D/R switching |
|---|---:|---:|---:|---:|
| CES retained panel, both administrative histories positive | 2,368 | 4.096697% | 5.102138% | 4.599023% |
| AP2024 pooled poll-close state-weight modeled-current-voter source | 79,516 | 3.420633% | 3.322722% | 3.372462% |

CES's switching directions have only 33 and 37 respondents, respectively.
AP's actual recalled House22 item uses 1R/2D, reversed from current House24;
`QVOTE2022S` is never used. Its frame uses `POLLCLOSE_STATE_WEIGHT`,
**not** the final-vote state weight used by the accepted fitted House bridge.
Pooling state-weight source cases does not yield a national population-weighted
estimate. Current modeled voter/source House response is not a candidate-specific
administrative vote. CES and AP differ in recruitment, retention, recall,
response timing, state composition and administrative selection. AP-minus-CES
gross switching is -1.226561 percentage points of **unmatched source concordance**,
not identified recall bias or population/model prediction error. No design CIs,
2026 correction, family reselection, verified staying home/entry or local allocation.
This historical window runs from a midterm to a presidential election; it is
not the requested 2024-to-2026 presidential-to-midterm transition.

Before this new joint calculation, source/code/test/design hashes and public
selection were locally frozen; this was not external public preregistration
or analysis of a previously untouched source. Public eligibility is restricted
to the two pooled primary 2x2 queries, with 30 raw cases required in **every**
cell. All other state/sensitivity/choice-only queries are held whole without
numeric complements. All 6,175 raw cases and complete separate-axis weighted
joints are accounted for privately, not relabeled nonvoters or dropped silently.

Immutable science 442761753, tag `participation-house-panel-validation-20261112-01`,
contains all permitted coarse sufficient inputs, 319 public decisions / two available
tables / 317 whole-table holds, eight coarse cells, five full outputs, seven exact
code/test files and coding-qualification records. Including the latter does not
override their inherited native-release/population-validation holds. The complete
ZIP is 35,562 bytes / 19 members, SHA256
`25d0dfe7a6b7332dd6f26620b36b96f277e57e8f319f38bc70b83757d9c3e2d3`.
Fourteen tests and 14,138 independent SQL/exact-fraction native checks pass.
Two fresh standard-library-only replays, with network/external commands blocked,
match all five public outputs; they do not repeat private extraction or model fits.
All 15 full release assets are anonymously byte-verified. Private respondents/
identifiers/fine cells remain local. The accepted three-family model, live map,
all old downloads and 49 missing independent state-population benchmarks remain.

```sh
python3 -S -W error code/scripts/reproduce_house_panel_validation.py \
  --archive /path/to/complete-analysis.zip --output /fresh/replay/path
```

Full results and scientific receipts:
`data/house-panel-validation/20261112-01/`; see [complete downloads](DATA.md).

## Three genuinely different model families

The November 12 comparison reuses the accepted ridge fits and all eight accepted
48-state simulation outputs byte-for-byte. Two new native-source fits use the
same predictor information, weights, state-stratified holdout seeds, frozen
endpoints, demographic disclosure masks and simulation grids:

- Native-categorical histogram gradient boosting: 100 iterations, 15 leaves,
  minimum leaf 100, learning rate 0.05, L2=1, no early stopping.
- Sparse extra-randomized trees: 128 trees, depth 12, minimum leaf 100, all
  features, no bootstrap, fixed seed 20261112.

The settings and source-only selection rule were locally frozen before these
new fits; this is not an external public preregistration.
An alternative must not worsen historical log loss, historical Brier or current
response Brier versus ridge; admissible models are ranked by historical log loss.
No current partisan-return error selects a family. **Ridge remains preferred.**

| Family | Current response log loss | Historical log loss | Historical Brier | 48-state margin MAE | Democratic two-party-share MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Accepted ridge | 0.47895891 | 0.74173593 | 0.35960468 | 6.12699827 | 3.06349914 |
| Histogram boosting | 0.47589286 | 0.74819312 | 0.36061296 | 5.74311543 | 2.87155771 |
| Extra-randomized trees | 0.58677669 | 0.80432412 | 0.35962708 | 6.06357405 | 3.03178702 |

Boosting's slightly better current-response prediction and lower return MAE do
not override its worse historical transfer. Historical transfer is now used for
family selection: it is **not an independent post-selection test**. Extra trees'
negative results remain published, not discarded. None independently validates
the decomposition's latent behaviors.

Each family has 50 state scenarios, 48 qualified comparisons, 1,600 group
decisions, 438 assumption cases, 250 state seeds and 1,500 demographic partition
seeds. The map compares families on one shared scale and can switch between
margin points and Democratic two-party-share-change points. All signed
contributions, errors and assumption ranges halve under share units. Gross
retention/switching percentages retain their original denominators and do not
halve. Family dispersion and assumption envelopes are not confidence intervals.

The full 35,332,487-byte/53-member scientific ZIP contains all three permitted
synthetic priors, every complete output/query, fitting and public replay code,
tests, and the **entire** accepted 48-state predecessor. Raw cases, individual
predictions, private fine cells and trained estimators remain local. Two fresh
standard-library-only offline replays under different hash seeds match all 31
public outputs, without private refits or baseline resimulation. Eight focused
tests, 52,258 independent numerical checks per new family and 3,788 independent
cross-family checks pass. An inherited ridge-only weight-description sentence
was corrected for tree fits before freezing public inputs; no numerical results
were recalculated for that metadata correction.

```sh
python3 -S -Werror code/scripts/reproduce_house_model_families.py \
  --root . --output /fresh/output/path
```

Public replay needs no numerical packages or network. Optional private-fitting
tests skip if numpy/scikit-learn are absent; the three public selection/units
tests still run. Authorized private fitting requires the original local survey
files and numerical stack, not public synthetic inputs in place of respondents.
The earlier ridge-specific methods and original checks below remain preserved.

The comparison interface is verified live at website `c2d1c19`, native
Pages run43184405254/artifact13927688816. Actual payload996829655/tar999424000
bytes both satisfy the strict cap; 69 unqueried assets and436 old downloads
match. Phone/desktop tests verify45,288 family/unit/group map values,3,060
baseline values,102 real pointer selections,all50 summaries, noJS/fault/retry/
late-office handling, preserved legacy views and48 layouts.
Full acceptance: `data/house-model-families/20261112-01/website-acceptance.json`.
Reviewed [phone comparison](media/house-model-families-20261112-01/phone-boosting-share.png)
and [desktop comparison](media/house-model-families-20261112-01/desktop-extra-trees-share.png).

The endpoint-only successor uses the official House Clerk 2024 baseline and the
unchanged November 7, 2026 current-source snapshot. It does not refit NORC.
The original November 11 release remains available unchanged.

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
candidate-vote volume, but not the current party split. Across 48 comparable
states its margin MAE is **6.12699827 points**. This changes the comparison set,
not the source fits. Texas projects R+4.5299 versus
held D+5.7080, a +10.2379-point error. Every state error is retained as model
error, never assigned to another behavioral component.

## Conditional reconstruction and exact demographic accounting

Forty-eight states have qualified held 2024/2026 same-office endpoints.
Two retain source-only scenarios and unavailable observed comparisons:
Alaska's leading current non-Republican nominee is explicitly Nonpartisan,
Maine's cross-year ranked-choice round compatibility is unresolved.
D.C. has no CHEP sample. None receives an invented recorded baseline.

The complete official House Clerk 2024 PDF supplies all 50 states/435 districts.
Its 1,279 candidate-party lines and 68 separate noncandidate accounting lines
were checked with a second PDF engine: 1,347 complete lines, 1,345 numeric cells,
two footnote-only counts and 8,082 checks. Blank, overvote, continuing and
exhausted quantities are not candidate votes; the 1,546,879 excluded accounting
units are not an extra voting population. Explicit same-nominee fusion lines
are combined, including Connecticut; Vermont's explicitly Republican/Libertarian
nominee is Republican-affiliated without inferred caucus or coalition assignment.
FL-20/OK-03 `(1)` counts remain NULL, not zero. The source notes explain that
unopposed names are not printed on the ballot; reported state count sums remain
separate from any invented count for those nominees.

In the preceding endpoint update, twenty-one anchored baselines changed and twelve comparisons were
newly anchored. Only those 33 states were recalculated. All numerical fields
and complete assumption/seed cases in the other 17 states were reused exactly.
The entire accepted predecessor and current native district controls remain
unchanged. These are frozen reported candidate counts, not updated November 12
counts, certified final totals, ballots or a measured turnout denominator.

The PA-only successor corrects an eligibility error, not a vote count.
The county-validation table unions reported district candidates with located
county name/party rows. Its 18 blank PA controls are county-validation-only
exceptions, not absent native votes. The complete accepted native export has
all 17 PA districts/34 reported candidates, matching every nonblank held
candidate control exactly without alias normalization. No county sum or missing
count is substituted. All 18 exceptions remain unchanged in the full query.
Provider district/state totals omit known county-source write-ins; those are
kept separate, not added to Other. This is not a complete Other-ballot count,
certified final return or participation measure. All 17 native clocks remain.

Only PA is recalculated in this successor; all 49 other states' numerical
fields and full assumption/seed inventories are reused. PA's before-conditioning
prediction is D+11.1572 versus reported D+13.3700, a +2.2128-point error.
Source fits and the frozen November 7 counts are unchanged.

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

Three frame scales (0.8/1/1.2) and three latent affinities (0.5/1/2) give 438
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
| Texas | +23.95 | +13.94 | +8.59 | +0.39 | +1.03 |
| Pennsylvania | +15.46 | +6.86 | +8.19 | +0.09 | +0.32 |
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
The successor also includes the full official PDF, native facts and exclusions,
all 50 endpoint decisions and exact old/new baseline comparisons.
Public simulation reproduction is complete and standard-library-only:

```sh
python3 -Werror code/scripts/reproduce_pa_house_native_controls.py \
  --package . --output /fresh/output/path
```

Python3.9 is the reference byte-reproduction toolchain. Two fresh network- and
external-command-blocked PA-only reproductions under different hash seeds match
all eight outputs. Five new native-scope behavior tests, 1,427 independent
SQL/native-control checks and 52,258 independent endpoint/rational-accounting/
demographic checks pass. Earlier complete science and its checks remain unchanged.
Private model-training reproduction requires the original user-supplied local
survey files and disclosure policy. Raw respondents, identifiers and private fine
source cells are not published or uploaded to CI.
