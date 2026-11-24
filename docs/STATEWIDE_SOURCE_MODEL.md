# Uniform statewide House source model

The primary statewide product uses one source-only method for all 50 states.
It is separate from recorded changes and return-constrained reconstructions,
whose candidate-coverage, election-stage and round holds remain unchanged.
D.C. has no CHEP sample; no estimate is supplied there.

## Interpretation

Both endpoints describe the CHEP2026 source-weighted frame, not either year's
observed statewide electorate. The 2024 House baseline uses the existing
AP2024 President/House association bridge and CHEP recalled presidential choice.
The three accepted response-model families and three association profiles are
reused without refitting respondents. No partisan returns constrain this
projection. That does not establish that the original source weights were
independent of election outcomes: their calibration targets remain unqualified.

This is not population calibration or multilevel regression and
poststratification. Input vintages are AP2024 and CHEP2026; the public fitted
priors do not supply native interview or fit dates. Publication and return
update times are not substituted for those dates.

The DRONU categories distinguish Democratic, Republican, Other, no House choice
and unresolved responses. Nonmajor choices remain Other; no coalition is
reassigned. N does not establish confirmed staying home, and U is not nonvote.
The synthetic transition matrix is not a set of linked individual histories.
No population counts, first-ever voters, deaths, migration or local allocation
are inferred. Demographic disclosure holds remain null, not zero.

The exact symmetric decomposition assigns denominator effects inside switching,
exit, entry, Other and unresolved contributions. Exit plus entry is the net
participation contribution. Democratic two-party-share changes and contributions
are half the D-R margin quantities. Gross retention uses its own previous-D/R
denominator and is never halved. Group contributions add to the state within
each supported dimension; overlapping dimensions are not additive causes.

Sensitivity spans all 27 combinations of three families, three association
profiles and half/base/double latent-choice affinity. These ranges are not
confidence intervals or complete sampling, recall, weight or transport uncertainty.
Negative changes and genuine zeros are retained.

## Complete data and reproduction

The complete fitted-input package includes all nine used public priors, exact
code and seven tests, every statewide and demographic query, all 27 sensitivity
cases, CSV exports, the saved display summary and checksums:

[Complete analysis ZIP](https://github.com/hanshanley/margin_of_error/releases/download/participation-statewide-source-20261124-01/complete-analysis.zip).

From a fresh extraction, using CPython 3.12 and no third-party packages:

```sh
python3.12 code/reproduce.py
```

This verifies the closed member inventory, runs the included tests, reproduces
all nine output files byte-for-byte and prints the regenerated complete ZIP pin.
It reproduces the public fitted-prior transformation, not private respondent
fitting. No raw respondents or private fine cells are redistributed.

The existing automatic runtime derives the same five compressed source artifacts
from its accepted rolling seed. Ordinary return revisions do not change these
artifacts, their source-input version or their unknown field dates. Complete
queries stay in the GitHub downloads; the consumer website receives only the
map code, immutable receipts and compact saved table. A separate immutable
fitted-input snapshot is the fallback if optional automatic source data fail.
