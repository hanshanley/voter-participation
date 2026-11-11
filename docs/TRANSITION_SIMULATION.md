# Conditional transition scenarios

This model simulates **keeping a party choice, switching parties, modeled
nonparticipation, prior-contest nonvote entry, Other and unresolved choices**.
It is a conditional source-frame model, not recovered respondent histories,
administratively measured staying home, causal persuasion or population turnout.

## Evidence and assumptions

The inputs are the complete previously released whole-state Civic moments,
the disclosed broad demographic participation inputs, 55 reviewed published
current-voter joint-question tables and the corrected return-comparison viewer.
The complete CPS historical state-frame packet is retained for qualification
decisions. No private respondents or private fine transition cells are inputs.

The user's `pre1870_pop` reference, pinned at
`af0c4a40e9e5562934adcbe30a6ec74d9d0f7593`, informs only the finite-budget,
seed-ensemble and conservation architecture. None of its historical population,
ancestry, fertility or migration inputs or assumptions enter this model.

For each of 50 source states, the model chooses a hypothetical 25-cell coupling
over D/R/Other/prior-contest-nonvote-or-modeled-nonvoter/unresolved labels.
It minimizes relative entropy to a prior that favors DD and RR persistence.
The constraints reproduce ten released, source-weight-normalized moments:
prior/current signed major-party mass, prior/current major-party mass, modeled
nonvoter mass and the five signed mechanism terms. Structural boundary moments
restrict support. A reduced-rank exponential-family Newton solve uses a
2e-10 original-moment tolerance, direct small contractions and a symmetric
Hessian eigensolve. Numerical warnings are not suppressed.

Matching these moments is an accounting check, **not validation**. Different
gross flows can have identical net contributions. A persistence strength is
therefore calibrated only against **gross** reported party switching among
current voters, without using its partisan direction or election-return counts.
The fixed candidate grid spans 0.5-256 in quarter-octave steps. The objective
averages squared errors within each state, then gives each state equal weight.
All office tables for the held-out state are excluded in each validation fold.
The original factors 1/4/16 and half/double the calibrated strength are retained.
The half/double envelope is assumption sensitivity, not a confidence interval.

The 55 tables cover 39 states: 27 Senate and 28 governor tables, no House table.
Transporting the House source model to these offices is an explicit assumption.
The selected strength is approximately 13.45. Its state-held-out gross-switching
MAE is about 1.39 percentage points, versus 1.40 for the fixed factor-16 model.
This is not material evidence of improved population prediction. Some governor
misses exceed four points, including roughly eight points in Wyoming. Survey
sample independence and population transport are not certified.

For each of 671 disclosed broad groups, the model rescales current nonvoter
versus other columns to the group's released modeled-nonvoter fraction.
It does not learn demographic prior-party associations. The remaining group
decisions stay unavailable, including D.C. and disclosure holds. Suppressed
categories are not completed by complement, and overlapping demographic
dimensions are not made into a joint population. RUCC is source county context,
not an observed individual location or a county-level estimate. Native income
is not certified household income.

## Simulation and reconciliation

A finite one-million-agent diagnostic budget has a 2,000-agent floor per state.
The remainder uses largest-remainder source-weight apportionment, not state
population counts. Five deterministic seeds conserve that budget separately
for every scenario. Multinomial cell draws are agent-equivalent; no individual
synthetic records are created. Group-conditioned draws are separate,
nonadditive diagnostic experiments. Draw counts are not data support or people.
Seed variation measures Monte Carlo error only, not survey/design uncertainty.

The five recalled-major-party gross outcomes form a complete partition:
retain, switch, modeled nonparticipation, Other and unresolved. Prior-contest
nonvote entry has a separate current-major-party denominator. Prior-contest
nonvote is not first-ever voting, new eligibility or no prior ballot.

All 113 reported return checks remain unfitted. For the 89 qualified same-office
comparisons, the full equation is:

```
reported same-office swing
  = synthetic signed source-frame mechanisms
  + normalized-margin denominator term
  + current reported-minus-model margin
  + recalled-prior-minus-reported-previous margin
```

Both frame differences remain unallocated; neither is attributed to people or
staying home. Unsupported previous comparisons remain null. Native clocks,
partial reporting, competition/geography qualifications and source scopes are
preserved. Candidate counts are not ballots.

All 2,754 historical CPS state/year/population decisions are retained. Native
unavailability is not zero; earlier citizenship definitions and population-frame
differences remain explicit. Repeated-cross-section voting marginals cannot
validate individual retention, switching or staying-home histories. The
historical joint-transition holdout is therefore explicitly unavailable, not
passed. Eligibility, deaths, migration and design confidence intervals remain
null. State estimates are not allocated to counties or precincts.

## Complete reproduction

Install the project's `simulation` extra, or the packet's exact
`requirements-simulation.txt` for numerical reproduction. Byte-identical results
require a compatible recorded numerical build; independent scalar checks use
explicit tolerances rather than claiming cross-platform bit identity.
The complete scientific ZIP includes
both whole predecessor analysis packets, the entire permitted demographic input,
the entire corrected comparison viewer, all simulation/validation code, focused
tests, every scenario/seed/group/held-out/historical decision, a compact viewer
and checksums. No acquisition session headers or publisher app are included.

```
python scripts/reproduce_transition_simulation.py \
  --archive complete-analysis.zip --output reproduction.json
```

The reproducer checks every member, blocks network/external commands, runs the
focused tests, reproduces every result and compact-viewer byte and invokes an
independent scalar verifier. That verifier imports neither NumPy nor the fitter:
it checks probability/support, original moments, relative-entropy stationarity,
all seed budgets, disclosure holds, gross partitions, source arithmetic,
state-blocked calibration and exact reported-swing reconciliation.
