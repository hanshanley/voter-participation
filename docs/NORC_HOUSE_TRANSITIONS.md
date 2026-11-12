# NORC-informed demographic House transitions

This model estimates how switching, entry/return, modeled nonparticipation,
Other-party choice and unresolved answers can account for state House margin
changes. It is an assumption-dependent explanation, not identified voter histories
or a causal effect. Moving from R+4 to D+12 is a +16 margin-point change,
equivalent to +8 Democratic **two-party-share** points, not +16 share points.

## Administrative participation and reported House choices jointly

The preceding experiments modeled administrative 3x3 and reported-House 6x5
pairs separately. The new source test learns their missing **cross-axis
dependence**, with a complete 270-category joint probability law. It does not
relabel reported choice as administrative participation.

Let `A=(A22,A24)` have nine positive/nonvote/unknown pair categories and
`H=(H22,H24)` have 30 reported-House pair categories. Reuse accepted paired
heads `p(A|X2020)` and `q(H|X2020)`. Fit only the new conditional ridge head
`r(H|A,X2020)` with the unchanged training settings, source weights and
2020-only predictor levels. During training, `A` is the conditional likelihood
factor. During test forecasting, enumerate **all nine hypothetical A values**
for every case; the actual future test history is not a forecast feature.

Compare:

1. Independent pairs: `p(A|X) q(H|X)`.
2. Conditional joint: `p(A|X) r(H|A,X)`.
3. KL projection of the conditional joint to the same accepted `p(A|X)` and
   `q(H|X)` margins for each case.

The third isolates cross-axis association while preserving both full pair
margins, including unknowns and contradictory reported/administrative histories.
It is a regularized conditional factorization, not a saturated unconstrained
270-class fit. Thirty new conditional heads reuse 60 accepted paired heads
from the earlier paired-source experiment, not refits of the later copula
heads. Same five original folds, two predictor levels and three native frames;
no parameter, family or model is selected against current return errors.

After target-free joint prediction, condition only on literal prior 2022
administrative and House categories. For prior administrative-positive cases
with reported D/R House choice, score all 15 possible 2024 administrative
P/N/U by reported D/R/O/contest-nonvote/U outcomes. For prior explicit
administrative nonvoters, score the same future categories with all prior
House reports retained. Separate known-future-P/N binary diagnostics are
**outcome-selected**, not population forecasts or proof unknowns are ignorable.

| Primary history source target | Independent pairs log loss | Fixed-pair joint log loss | Independent Brier | Fixed-pair Brier |
|---|---:|---:|---:|---:|
| Full four-axis, 270 categories | 2.371022 | 2.280635 | 0.676764 | 0.666091 |
| Prior nonvoter, full 15 future outcomes | 1.551515 | 1.483908 | 0.646315 | 0.617133 |
| Prior nonvoter, known-future-P/N diagnostic | 0.490998 | 0.460688 | 0.310181 | 0.292315 |
| Prior positive/major choice, full 15 future outcomes | 0.661000 | 0.664968 | 0.270781 | 0.269834 |
| Prior positive/major choice, known-future-P/N diagnostic | 0.069624 | 0.070773 | 0.025155 | 0.025212 |

These are different scoring targets; do not rank their raw loss magnitudes
against each other or the earlier 30-class House tests. The full joint and
prior-nonvoter scores improve, but the prior-major-voter log score and
known-history drop-off diagnostic worsen. The full-15 Brier improves in that
cohort, so the result is a proper-score trade-off, not uniform improvement.
Adding tested demographic/geographic predictors still does not beat simpler
history. No staying-home parameter is promoted.

Primary history log-loss fold compositions reverse the full-joint advantage
in 0/126, prior-nonvoter future-15 in 9/126 and entry known-P/N in 21/126.
Prior-major-voter full-15 worsens in 93/126 and drop-off known-P/N in 120/126.
All 18,144 frame/feature/model/cohort/metric stresses and their multiplicities
remain; training sets overlap, so these are **not confidence intervals**.

### Source cohorts, disclosure and a calibration counterexample

All 6,175 raw cases remain retained. Each frame trains/scores only its native
positive weights; primary post24 evaluations have 4,015 cases overall,
2,760 prior positive/major-House cases and 403 prior explicit nonvoters.
Missing or zero weights are not replaced with average weights, and unknown
responses are not recoded to nonvote.

The frozen disclosure rule requires every cell of a whole pooled primary
reference table to contain at least 30 raw cases. The six-cell prior-major
table fails and is held **whole**, without native rare/fine/source-state
disclosures. The prior-nonvoter reference qualifies: 230 positive, 128 explicit
nonvote and 45 unknown future histories. Their weighted source shares are
71.144209%, 16.370869% and 12.484922%, not population re-entry rates.

Projected history predicts 72.336692% positive, versus baseline 70.843548%
and reference 71.144209%. Aggregate entry calibration worsens even while
individual proper scores improve. Closer pooled calibration is not a substitute
for scoring each case or a reason to suppress this negative result.

For primary source-predictive stress, simulate 10,000 independent draws from
each pooled coarse predictive mixture under five common seeds, totaling
600,000 synthetic draws. These are illustrative model draws, not real persons,
sampling variance, survey uncertainty or confidence intervals.

### Limits, complete outputs and reproduction

Prior-2022 conditioning is retrospective: availability of the later matched
administrative record before 2024 is **not established**. This is not archived
prospective validation. Retained-2020-adult recruitment, omitted newly eligible
adults, postwave weights, conditional shared-item House codes and imperfect
matching remain. Administrative P/N/U is not candidate-specific ballot truth;
reported House choices and conflicts are kept literally. Source administrative
nonvote cannot be transferred as the 2026 NORC voting-likelihood class.
No first-ever/eligibility/death/migration, state-population benchmark or local
allocation is identified. Existing live maps, default and 2026 forecasts stay
unchanged; no unnecessary website rebuild was run.

Immutable science **443141393**, tag
`participation-house-four-axis-20261112-01`: **63,962,523 bytes / 29 members**,
SHA256 `38ec0cc2532385460fe8d1ff4eace310061dd84f79282e54070724de58a76527`.
Includes the entire accepted 63,651,646-byte predecessor, all 540 scored
queries, 216 pooled scores, 60 predictive queries, 54 estimates, 270 simulation
rows, all stresses, permitted sufficient inputs, exact code/tests and proofs.
Nine focused tests / 3,650 independent cache, isolation, math.fsum,
pair-margin and dual checks pass. Two fresh blocked-network/command
standard-library replays match all nine outputs; extracted tests pass six
with three optional numerical cases skipped. All **21 full assets** verified.
Scientific source `a2b3f9e854de4c35fc42958861579d561820662c`;
design/code were frozen before new fits, not externally preregistered, and
the source/earlier pair results were already explored.

```sh
python3 -S -W error code/scripts/reproduce_house_four_axis.py \
  --archive /path/to/complete-analysis.zip --output /fresh/replay/path
```

## Nested fixed-marginal dependence calibration

The earlier independent/paired comparison below changes the fitted joint and
can also change marginal predictions. The new experiment instead freezes
**every case's original 2022 and 2024 predicted House-response margins**.
For case `i`, let `p_i(a)` and `q_i(b)` be the accepted six- and five-class
predictions. Define `K_theta(a,b)=theta` for D-D/R-R and 1 otherwise, and solve

`Q_i(a,b) = u_i(a) p_i(a) q_i(b) K_theta(a,b) v_i(b)`

subject to `sum_b Q_i(a,b)=p_i(a)` and `sum_a Q_i(a,b)=q_i(b)`.
Positive iterative proportional fitting gives the dual row/column scaling
certificate. Theta=1 is exactly the original outer product. The D/R
cross-product odds multiplier is **theta squared**, not theta and not a
retention percentage. Other/nonvote/unknown classes remain distinct; no
administrative-N persistence parameter is inferred from this kernel.

For each of five original outer folds, fit three inner-fold marginal heads
**only inside that outer training set**. Do not calibrate on the other four
overlapping outer-OOF predictions: their training sets contain this outer test
fold. Theta in [.25,.5,1,2,4,8,16,32,64] minimizes native-weighted full
30-class inner-OOF log loss; ties within 1e-12 prefer closest log(theta) to zero.
Then apply it to the unchanged accepted outer marginal predictions and score
the untouched outer fold. Same 2020-only predictors, native weight frames,
training-only vocabulary/support regularization and ridge C=.15 remain.
This adds 180 inner heads; 60 accepted outer heads are reused, never refitted.

| Primary source predictors | Original log loss | Calibrated log loss | Original Brier | Calibrated Brier |
|---|---:|---:|---:|---:|
| History only | 1.313660 | 1.263987 | 0.483039 | 0.477228 |
| History plus age/education/survey state | 1.348023 | 1.300594 | 0.492568 | 0.485929 |

Primary history selections are 8,4,8,8,8 (median 8); demographic selections
4,4,8,4,4. The tested richer predictors still do not beat simpler calibrated
history. Maximum case margin error is below 2e-12; independent proper scoring,
dual certificates and exact accepted-baseline probabilities pass. The
selected-major conditional Brier improves .155258 to .143845 for history.
Under the separately matched source margins, gross switching is 4.785352%
for calibrated history versus 4.599023% in the already public source reference.
This diagnostic is not the calibration target or independent population truth.

### Conditional current-election stresses, including the negative result

The policy frozen before these new fits allows transport only if primary
history full-pair log loss improves, Brier and selected-major Brier do not
worsen, margins/duals pass and median theta exceeds one. It passes here.
The history-only source was fixed before this test because the preceding
proper-score comparison favored it, not because of current-return error.
Requested sqrt(8) and 8 give two **association stresses**, not new model
families or validated transfers of this per-case parameter.

The current priors have richer predictors, a different election direction and
different recruitment/response frames. Stress therefore acts **after state
aggregation**, not on the original 2026 persons. Each demographic partition
is projected jointly to its original group-by-previous, group-by-current and
common state 5x5 margins. Cell feasibility bounds and backoff exponents
1,.5,.25,.125,0 use only synthetic source constraints before reading current
return comparisons. Zero recovers the exact original. The stronger ridge
and boosting profiles each need one state's backoff; actual strengths are
retained and displayed, not replaced with the requested strength.

Preserving unconditional current margins does **not** freeze prediction after
the existing previous-row and candidate-volume calibration. Those honest
preconditioning errors are:

| Family | Original margin MAE | Attenuated | Stronger |
|---|---:|---:|---:|
| Ridge | 6.126998 | 6.276248 | 6.178784 |
| Histogram boosting | 5.743115 | 6.243356 | 6.524791 |
| Extra-randomized trees | 6.063574 | 6.529695 | 6.989285 |

**Neither current stress improves any family's 48-state return prediction.**
Do not select a profile using these errors or replace the original default.
All effects still reconcile under return conditioning; that is a constraint,
not predictive or behavioral validation. The map integration is now verified
live after exact artifact and production checks, not just a local build.

All six new runs preserve the same 50 states, 48 comparisons, AK/ME holds,
source masks, direct recalled-2022 scenario and central accounting frames.
State and group-year source margins stay fixed; switching versus participation
allocations change. Entry/return does not prove first-ever voting, and model
nonvote is not administrative staying home. The retained-2020-adult panel,
conditional candidate-code bridge, omitted newly eligible adults and
postwave weighting qualifications remain. No confidence intervals, identified
causes or state-to-precinct estimates are manufactured.

Immutable science **443019940**, tag
`participation-house-fixed-copula-20261112-01`, contains 63,651,646 bytes /
124 members: both entire accepted predecessors, all 270 curves / 30 decisions /
60 outer rows, every six-profile-run state/group/assumption/seed output,
450 comparisons, all permitted inputs, exact code/tests and proofs. SHA256
`08273545ef2886a3994ea2f4a7c7083f7a780e78c3335c88b1d3665cc6b0db72`.
All 22 full assets anonymously verified; 15 scientific tests, 4,797 independent
nested checks and 462,020 current-profile accounting/margin checks pass.
Two fresh `python -S -W error` replays with blocked network/commands reproduce
all 60 outputs from 12 published projected inputs, independently checking
their year margins, partition coherence and state dual certificates first.
The replay reruns only the six new current simulations, not baseline
simulations or private fitting. Projection recomputation requires NumPy;
the original failed replay and dependency-only correction are preserved.
Scientific implementation `dd28869d0985080f6ec2b31f90d6682f47033e90`;
unchanged numerical viewer pin `3c99ff2712e266f16860551ab65957c647956753`.
Native persons, predictions, coefficients and fine cells remain private.

Website `94db6c0c098842b01cf0a33a090bf62c30cf818c` / Pages
**43233632514** / artifact **13951483145** passes actual payload
**996,851,521** and tar **999,444,480** bytes. All 69 unqueried assets and
436 old complete downloads match. Real production checks cover 90,576 new
profile values, 45,288 original family values, 3,060 baseline values,
all 50 state summaries, 102 actual pointer selections, 48 responsive/tab
cases, no-JS, failure/checksum/retry/cache and late-profile/office isolation.
Active-profile errors and actual feasibility strengths remain visible;
family, state, group and unit selections survive profile changes.
Phone and desktop production views were inspected. No source fits, baseline
simulations, old numerical outputs, default selection or geography changed.

```sh
python3 -S -W error code/scripts/reproduce_house_fixed_copula.py \
  --archive /path/to/complete-analysis.zip --output /fresh/replay/path
```

## Held-out dependence test and why matching margins is not enough

The next historical test predicts both 2022 and 2024 source outcomes from
**2020-only** survey predictors: contemporaneous President response, approximate
calendar-age, literal education code and survey state. It does not use later
reported House choices, later administrative histories, carried 2020 recall
profiles or 2026 returns as predictors. Five prior-President-stratified folds
are shared across every model and native weight frame. Vocabulary and source
weight normalization use only positive-weight training cases.

Five structural hypotheses are compared, not five new statistical families:
pooled President20-stratum paired frequencies; independent versus paired ridge
with President20 only; independent versus paired ridge adding 2020 age,
education and state, with President-by-age/education interactions. Ridge C=0.15,
solver settings and support regularization are fixed. Native training weights
are divided by their training mean; evaluation uses native weight ratios.
The primary frame is `commonpostweight_24`; the guide recommends 2024 weights.
Earlier `commonpostweight_22` and `vvweight_post_22` are explicitly nonrecommended
2024-frame sensitivity experiments, not certified alternative population weights.

Administrative responses form a full 3x3 pair (positive / explicit nonvote /
unknown in each year). Reported House responses form a full 6x5 pair, preserving
2022 reported-election nonvote separately and forbidding that unsupported code
in 2024. Independent heads multiply two marginal predictions; paired heads
learn the corresponding 9- or 30-class joint distribution. Administrative and
House pairs are still modeled separately: this is **not** a learned 270-state
joint dependence across all four axes. Contradictions are not repaired.

Absent training classes receive an explicit training-only Dirichlet prior
(alpha=0.5 per class), mixed into ridge probabilities by `1/(training_n+1)`.
This is fixed support regularization, not post-score flooring or observed
support. Pooled history rows shrink by 20 normalized training-case weight units
toward the similarly smoothed global distribution. All unknown cases remain.

Full-pair log loss and multiclass Brier scores are evaluated out of fold.
Known-positive/nonvote administrative pairs are separately renormalized/scored,
so predicting missingness alone cannot explain that diagnostic. The previously
published both-positive-history/both-major-House cohort supplies a separate,
explicitly outcome-selected conditional House-pair diagnostic.

| Hypothesis, primary weights | House pair log loss | House pair Brier | Administrative pair log loss | Administrative pair Brier |
|---|---:|---:|---:|---:|
| Pooled-history pairs | 1.278311 | 0.476766 | 1.095872 | 0.478363 |
| Independent history | 1.313660 | 0.483039 | 1.262932 | 0.505718 |
| Paired history | 1.275865 | 0.476735 | 1.095157 | 0.477814 |
| Independent demographic/geographic | 1.348023 | 0.492568 | 1.303602 | 0.520227 |
| Paired demographic/geographic | 1.315931 | 0.487600 | 1.115513 | 0.491573 |

Pairing improves matched-feature comparisons here. **Adding the tested
demographic/geographic predictors does not improve overall prediction versus
the simpler paired-history model.** These expanded 9-/30-class source scores
cannot be ranked against the accepted 2026 model's different five-class scores.
No family or live default is reselected from this table.

### Identical margins, different gross switching

OOF House-pair predictions are renormalized to four D/R pairs within each
already selected both-positive-history/both-major-choice case, then aggregated
with primary source weights. These are conditional selected-cohort forecasts,
not predictions of who would enter that cohort or of population switching.
The aggregate is scaled to its known source weight total. A separate stage
matches only the exact previously public D/R row and column margins.

For four cells and fixed margins, let `x=DD`, `r` be previous D weight,
`c` current D weight and `T` total. Then `DR=r-x`, `RD=c-x`,
`RR=T-r-c+x`. The matching stage solves
`x*(T-r-c+x)/((r-x)*(c-x)) = forecast_odds_ratio`.
It preserves the forecast's association rather than fitting observed switching.

| Hypothesis | Gross switching after identical-margin matching | Reference gross switching |
|---|---:|---:|
| Pooled-history pairs | 4.598943% | 4.599023% |
| Independent history | 12.035204% | 4.599023% |
| Paired history | 4.549400% | 4.599023% |
| Independent demographic/geographic | 11.294996% | 4.599023% |
| Paired demographic/geographic | 4.620939% | 4.599023% |

Thus matching margins can coexist with seriously wrong gross flows in this
source diagnostic. The richer paired model's closer aggregate rate does not
override its worse proper scores relative to simpler paired-history.
Near-perfect pooled aggregate calibration is not identification of individual
histories or validation on an independent external sample.

### Sensitivity, correction history and complete reproduction

All 126 compositions of five fold draws are evaluated with their multinomial
multiplicities, summing to 3,125 ordered draws. The complete 5,040 paired-minus-
independent score rows are fold-composition stress tests, **not confidence
intervals**: training sets overlap and folds are not independent sampling units.
The primary demographic comparison reverses its full-House advantage in
21 of 126 unique compositions for log loss and 14 for Brier. Known-history
Brier also reverses in six. The selected-major House diagnostic favors pairing
throughout this grid, but that is not a significance or population claim.
No per-person losses, predictions, coefficients, features or native fine cells
are released. Published sufficient inputs are broad fold-level score sums and
synthetic selected-cohort forecasts; the exact public reference is reused,
not supplemented with recoverable raw source subtables.

The original design/code/test hashes were frozen before the first new fit.
It was not external public preregistration, and the source/reference were
already explored. After 72 successful component fits, finite weighted `matmul`
reductions raised numerical flags despite agreement with independent product
sums and `math.fsum`. Only score/forecast reductions changed. AST-bound cache
adoption retained all successful probability arrays unchanged; 108 remaining
fits completed, none repeated. Both policies, the original source, diagnostic
and adoption proof are preserved, not silently rewritten.

Scientific source `a90a2c6fb881fe1123c5da4a7f232d0d4d33e02b`; immutable
science **442867090**, tag `participation-house-paired-oof-20261112-01`.
The 163,404-byte / 29-member ZIP includes the entire accepted predecessor,
all permitted inputs, 75 model/fold/frame rows, 100 pooled scores, 40 synthetic
cells / 10 stages, 15 decisions, all stress rows, nine exact code/test files
and all seven outputs. SHA256
`a48dcae4c99911cf8c3dc05ef39bde1617d4abb12589d99d47dec15649c97ed8`.
Thirteen tests / 27,479 independent native-row, predictor, weight, cache,
`math.fsum` and iterative-IPF checks pass; two fresh blocked-network/command
standard-library replays match every output. Without numerical packages the
five private-stack tests skip, while eight feature/public-arithmetic tests run.
All 19 full assets are anonymously byte-verified.

```sh
python3 -S -W error code/scripts/reproduce_house_pair_oof.py \
  --archive /path/to/complete-analysis.zip --output /fresh/replay/path
```

Conditional common-item coding, retained-2020-adult selection, postwave weighting,
future-cohort selection and differing historical predictors/window remain.
This midterm-to-presidential test is not a replication of the richer 2026
predictor set or validated presidential-to-midterm transport. Native House
reports are not candidate-specific administrative truth. No current source
marginal, accepted model, live map, earlier download or precinct allocation
changed in this earlier experiment. The nested fixed-marginal step is now
complete in the section above; no pooled odds ratio is transported as a
validated 2026 parameter.
Full results: `data/house-paired-oof/20261112-01/`.

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
