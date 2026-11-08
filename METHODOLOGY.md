# How we estimate voter participation

We estimate **whether people participate**, separately from candidate preference.
Historical self-reports, current survey models and administrative counts answer
different questions; we do not combine them into one supposedly observed turnout
rate. The project does not reproduce or train on NYT's proprietary estimates.

[Overview](README.md) | [Data](docs/DATA.md) |
[Reproduce](docs/REPRODUCING.md) | [Technical source notes](SOURCES.md)

## 1. Define the quantity before calculating it

Every estimate retains its election, geography, source date, population and
numerator definition.

| Quantity | Numerator / denominator | Interpretation |
|---|---|---|
| Survey-reported participation | Weighted reported voters / matching adult citizen or resident population | Self-reported voting, not an administrative voter count. |
| Survey-modeled participation | Weighted source-defined modeled voters / full matching study group | A source-weighted model share, not verified completed voting. |
| Administrative participation | Qualified participation count / matching registration or declared population count | A source-specific rate; preliminary reporting remains preliminary. |
| Candidate contest totals | Votes recorded for candidates in that contest | Election context, not ballots, unique voters or demographic participation. |

Adult residents, adult citizens, active registrants and all registrants are
different frames. CPS voting/registration marginal ratios do not establish an
individual registered-voter joint or administrative registered-voter turnout.

## 2. Estimate group rates with the source's weights

For a group `g`, participation class `v`, and source weight `w`:

```text
p(g, v) = sum(weight in group g and class v) / sum(weight in group g)
```

Published historical tables retain their native weighted counts or percentages.
Where respondent-level inputs are permitted, we apply the study's supplied
weights and native definitions, rather than reweighting to obtain a desired result.
AP state/national and poll-close/final weights remain separate. Civic's pooled
source is not certified as a national population estimate.

Unknown participation and demographic categories remain explicit. Missing
administrative matches do not establish nonvoting; legacy merged no/unknown
responses are not split into observed nonvoters. Distinct demographic dimensions
are not multiplied into synthetic joint groups or summed as disjoint populations.

## 3. Connect rates to counts only with a defensible frame

First match the election, geography, register status, timing and source meaning.
Check native totals, parent/child accounting and reporting coverage; retain
conflicts rather than repairing a source to fit another.

Where a reviewed registration count `R` and survey share `p` support a scenario:

```text
estimated participants = R * p
```

This is **conditional on exchangeability to that exact registration frame**,
which has not been independently established. The corresponding modeled
nonparticipant count is not observed staying home. Unknown outcome mass is
retained according to the source, not relabeled nonparticipation.

A statewide register supports only its qualified statewide scenario, not
demographic counts without matching group denominators. We do not manufacture
registration counts from voting-age population or scale unmatched national
survey frames. Returned/processed ballots and source-labeled "Votes Cast" are
not automatically qualified cast ballots.

## 4. Compare elections without manufacturing a panel

Compare presidential elections with presidential elections, and midterms with
midterms. Preserve changes in age, citizenship, race, education, question wording
and coverage; hold incompatible comparisons rather than silently harmonizing them.
Current snapshots retain actual cutoffs and cannot establish final turnout change.

Repeated cross-sections describe different sampled electorates. Recall/current
survey tables are source-frame diagnostics, not tracked original populations.
The separate choice-change analysis preserves unknown/Other and the exact
denominator-change term; it does not identify causal persuasion, first-ever voting,
new eligibility, deaths or migration.

## 5. Test projections against simple baselines

The implemented historical prototype transfers a group's average turnout
log-odds gap from its three preceding same-type elections. National turnout is
carried forward from the preceding same-type election, never supplied from the
held-out target. Its benchmark carries forward the group's previous rate.

**That prototype failed its historical screen:** mean absolute error was
4.22 percentage points, versus 4.17 for carry-forward. Its 2026 predictions
remain withheld. These archived-table year holdouts are not release-vintage
forecasts or independent population validation.

The later AP/Civic source-weighted estimates and conditional registration
scenarios are separate analyses, not evidence that the failed prototype passed.
A richer hierarchical participation model remains proposed, not fitted.
The [original protocol](docs/RESEARCH_PROTOCOL.md) records its specification.

## 6. Map only what the geography supports

Precinct participation requires matched election-year participation counts,
registration/population definitions and boundary evidence. Missing boundaries
do not borrow another year's map. Unreconciled counts or zero denominators have
no displayed rate.

State survey rates are never allocated to counties or precincts. Candidate-result
layers are labeled separately; demographic population composition does not reveal
which residents voted. A map's available shapes are not proof of complete coverage.

## 7. Show uncertainty and missingness honestly

Use native reported uncertainty where applicable and retain its scope.
Weight-only effective sample size and support screens are diagnostics, not
survey-design confidence intervals or guarantees of precision.
Assigning explicit unknown responses to different outcomes is a sensitivity
scenario, not a confidence interval or a bound on actual turnout.

No generic confidence interval is fabricated when survey design, model error,
population transport or reporting coverage is unresolved. Outcome-calibrated
survey weights also mean agreement with final counts may not be independent
validation. Unsupported rows remain visible as missing or held.

## 8. Make each result reproducible

Complete packages preserve permitted sufficient inputs, source hashes, every
matched/unmatched query, code, tests and results. Original native values and
earlier releases remain available. Private respondent records and private fine
cells are excluded; selected aggregate packages reproduce from their complete
permitted aggregate inputs.

See the [data catalog](docs/DATA.md) and [reproduction guide](docs/REPRODUCING.md).
Detailed source exceptions belong in the [source ledger](SOURCES.md), not in the
website's short Methods tab. Outstanding evidence needs are in
[Remaining work](REMAINING.md).
