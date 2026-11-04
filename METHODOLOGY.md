# Independent participation estimates: research protocol

We study whether people vote, not which candidate they support. No NYT estimates,
article tables, proprietary model outputs, poll responses or commercial voter-file
records are ingested, used as training targets, or used to tune this approach.
Public primary data remain attributed to their original producers; the
normalization, model specification, diagnostics and conclusions are our own.
The supplied NYT description is conceptual context, not a data source or an
implementation we claim to reproduce.

## What we can already measure

- Historical national/state CPS self-reported turnout, with the original adult
  citizen or adult resident denominator identified.
- NC historical aggregate participation divided by matching election-time
  registrations, with unreconciled records flagged rather than manufactured.
- Preliminary 2026 administrative ballots and available early-voting demographic
  counts, with state/mode/source dates and explicit missing coverage.

These are different populations and reporting stages. Early-voting composition
cannot identify full-election demographic turnout, and a statewide total alone
cannot identify how that total divides among demographic groups. A precinct's
demographic population mix does not identify its individual voters' behavior.
No current candidate results are needed for a participation model.

## Implemented first experiment

`python -m scripts.model` runs a fully reproducible historical baseline experiment.
It uses the archived `national.json` observations and preserves their source
workbook/row references, training years and an input SHA-256. It does not retrieve
new data, fit to NYT figures or generate 2026 estimates.

The candidate is a deliberately small log-odds-gap transfer model:

```
gap(g,k) = logit(CPS_turnout(g,k)) - logit(CPS_turnout(all,k))
predicted_turnout(g,t) =
    logistic(logit(CPS_turnout(all,t-4)) + mean(last 3 same-type gap(g,k)))
```

Train on 2000 onward, or 2004 onward for race to avoid the earlier classification
break. Keep presidential and midterm elections separate. Preserve native CPS age,
race, education and sex categories; do not relabel them to match a publisher's
bins. Race and Hispanic-origin categories overlap and are not an electorate
partition. No synthetic joint demographics are created from marginal tables.

Each target election uses only earlier election-year observations, with at least
three same-type training elections and an observed immediately preceding
same-type election. Test elections start in 2012, where supported. The benchmark
simply carries forward the group's rate from four years earlier. The target
election's national turnout is **not** a model input. Store every held-out
prediction and error, not just favorable averages.

The following working research criteria are fixed before executing the experiment:
at least 10% lower mean absolute error than carry-forward overall; lower error in
both election types and every demographic dimension; no worse error in the latest
held-out midterm; and no group's mean absolute error above 5 percentage points.
These are screening thresholds, not universal reliability criteria. Errors are
equal-weight group/election errors; overlapping groups are not independent.
Current archived table revisions are used, so this is not an as-of-release-vintage
simulation. CPS observations are survey-reported comparison targets, not validated
turnout ground truth. These tests are initial diagnostics, not untouched
confirmation data for future model-selection iterations.

Even a passing historical screen would not authorize publishing 2026 estimates.
The output always includes an empty `estimates_2026` list and an explicit
withholding decision. Historical persistence alone cannot tell us whether groups
shifted their participation in the current election. Failed screens stay public.

## Next model: two distinct denominator tracks

### Public joint-demographic inputs now acquired

`python -m scripts.cps --download` acquires the Census November 2022 and 2024
public-use Voting and Registration survey ZIPs, technical documentation and
original source catalogs. `python -m scripts.cps` verifies their saved hashes and
rebuilds the audit offline. These are anonymized public survey responses, not
commercial voter files, registration records or a publisher's modeled estimates.
The source-specific fixed-width layouts and final weight PWSSWGT (four implied
decimal places) are checked against both years' documentation, attachments 6/7.

The universe is age 18+, citizenship codes 1-4 and civilian person type 2.
Observed joint cells cross state, native age bins, sex, education and a mutually
exclusive race/Hispanic-origin partition. Published all-race and Hispanic-origin
marginals overlap and remain separate comparison series. No joint cell is
fabricated by multiplying marginal shares. Every included observation contributes
to exactly one joint cell; all exclusive partitions reconcile to the national
count and weighted population.

PES1 yes, no, don't know, refused, no response, and supplement noninterviews
remain distinct. Reported voting is weighted "yes" divided by all civilian adult
citizens, matching the published-table denominator, not only supplement
respondents. A yes-only respondent denominator is not used. The output also
retains respondent-only sensitivity and a logical range assigning unknown
outcomes no/yes. That range is **not a confidence interval**, does not resolve
over-reporting, and does not include people outside the sampled universe.
Weight-only effective sample size is diagnostic, not design-based precision.

All matching archived national age, race, sex, education and overall rates must
reconcile within 0.15 percentage points before promotion; that tolerance allows
published rounding and public-use revisions, not calibration to external modeled
results. The published references, exact differences and all source hashes remain
downloadable. These checks audit input handling, not predictive reliability.
Most fine joint cells have small samples: their research counts are retained,
not presented as precise subgroup turnout estimates.

`public/data/cps/` contains every observed joint cell, every projected marginal,
all published comparisons, complete audit JSON and a ZIP with **all** observations,
original public survey ZIPs, documentation, catalogs and comparison inputs.
No household/person identifiers or individual records are projected into the
website tables. The untouched public Census originals remain in the full research
download for reproducibility.

This is the input stage of the next model, not a fitted hierarchical model or an
improvement claim on the first experiment. Replicate weights/design-based
uncertainty, compatible ACS joint population inputs, additional training years and
a prospectively frozen confirmation specification are still required.
It produces no 2026 rates and does not retune the existing backtests.

### Denominator-specific estimation

1. **Registered-voter administrative track.** Where official aggregate
   participation and registration counts cover the same election, geography,
   demographic bins and registration-status universe, calculate direct rates.
   Preserve unknown demographics as a category. Reconcile cells with source
   totals and retain incomplete reporting as incomplete. Date-mismatched weekly
   registration and daily ballots do not become election-day turnout rates.
2. **Citizen-population survey track.** Fit a participation-only hierarchical
   logistic model to public CPS Voting and Registration microdata, respecting
   survey weights and available survey-design information. Candidate predictors
   are age, education, sex, race/ethnicity, state, election type/year, and supported
   interactions. Partial pooling must address sparse cells. This is a proposed
   next model, not an implemented or validated claim.

For the second track, estimate population cell counts from public ACS tabulations
or PUMS with the same citizen/adult definitions and geography; retain reference
years and sampling error. Joint cells must come from observed joint data or an
explicitly tested synthesis, not multiplication of independent marginal shares.
ACS citizen voting-age population is not automatically legal voting eligibility.
Keep civilian/noninstitutionalized scope differences explicit rather than
silently calibrating unlike populations. Registered-voter and citizen-population
rates are not interchangeable labels in one regression.

For compatible population counts N and cell probabilities p:

```
group turnout = sum(N_cell * p_cell) / sum(N_cell)
group electorate share = sum_group(N_cell * p_cell) / sum_all(N_cell * p_cell)
representation index = electorate share / matching population share
```

Shares require exhaustive, mutually exclusive cells from a single coherent
universe. Do not construct them by summing overlapping race/ethnicity series.
Margins of error must propagate survey design, population estimates, reporting
coverage and model uncertainty. Account explicitly for CPS missingness and
over-reporting; do not label a sampling-only interval total uncertainty.

## Release gates for a 2026 demographic nowcast

- Independently acquired, documented and reusable inputs with immutable originals,
  dates, hashes and complete downloadable observations.
- Harmonized population/numerator scope, bins and geographic coverage; audited
  registration timing and preliminary ballot completeness.
- Past-election holdouts by year and geography, prespecified simple baselines,
  errors by group, uncertainty coverage, and sparse/missing-cell sensitivity.
- A new confirmation holdout or prospectively frozen specification after model
  selection; do not keep tuning on the same reported backtests.
- Evidence about 2026 turnout rather than just past behavior: compatible current
  administrative totals and representative current participation information,
  or a clearly labeled historical scenario rather than an observed nowcast.
- Separate observed, estimated and unassessed places. No nationwide demographic
  rate extrapolated from a convenience subset of early-voting states.
- No precinct demographic rate from county counts or ecological assumptions.
  Precinct maps require validated participation/registration counts and correct
  election-year geography, as in the existing NC historical pilot.

Until these pass, publish the historical observations, source coverage, method
and validation results, not unsupported 2026 demographic percentages.

## Primary references

- U.S. Census Bureau, public CPS Voting and Registration datasets and technical
  documentation:
  <https://www.census.gov/data/datasets/time-series/demo/cps/cps-supp_cps-repwgt/cps-voting.html>
- U.S. Census Bureau, Citizen Voting Age Population by Race and Ethnicity:
  <https://www.census.gov/programs-surveys/decennial-census/about/voting-rights/cvap.html>
- NCSBE, aggregate and individual voter-history data definitions:
  <https://www.ncsbe.gov/results-data/voter-history-data>
- NCSBE, election-specific registration statistics and timing:
  <https://www.ncsbe.gov/results-data/voter-registration-data>
- Tang, Hillygus and Reiter (2022), *Using auxiliary marginal distributions in
  imputations for nonresponse while accounting for survey weights, with application
  to estimating voter turnout*: <https://arxiv.org/abs/2209.05220>.
  This motivates explicit nonresponse/over-report sensitivity, not a claim that our
  small baseline implements their imputation procedure.
