# 2026 modeled margin contributions

These are **conditional source-weighted estimates**, not observed individual
switching, administrative staying home or causal persuasion.

## Inputs and scope

The bridge combines NORC's existing whole-state 2024-recall/2026 model moments
with held candidate returns: 50 House state aggregates, 35 Senate races and 28
governor county frames. It uses 55 qualified office-specific main SSRS tables
where available. Remaining cross-office switching explicitly transports the
NORC House model. D.C. has no NORC sample; state models are not allocated to
districts, counties or precincts.

House controls can have missing candidate totals. Governor sums describe the
supplied county frame. Native clocks, rounds, partial reporting and literal
party labels remain explicit; candidate votes never substitute for ballots.

## Accounting, not a forced two-way explanation

Each estimate keeps switching, modeled nonparticipation, no-prior-contest-vote
entry, other choices, unresolved choice and the normalized denominator term.
The **return/frame gap** separately absorbs source-model, selection, timing and
office mismatch. It is not labelled extra persuasion or staying home.

The model's recalled baseline is **2024 President**, not automatically the last
election for the selected office. A separate prior-office/frame term is shown
when a supplied same-office previous comparison exists. No historical partisan
composition is fitted. The model's use of the returns is not independent
validation against those same returns.

## Uncertainty and interpretation

Nine explicit scenarios multiply switching and nonparticipation contrasts by
0.5, 1 or 1.5 and recompute the gap. These are **partial strength-sensitivity
ranges**, not sampling confidence intervals, identification bounds, feasible
individual histories or exhaustive model uncertainty.

Source-weight units are not people. Prior contest nonvote does not establish
no ballot, first-ever voting or new eligibility. Death, eligibility and
migration remain unknown. Unknown/Other and signed opposing effects survive;
zero net change has no defined attribution percentage.

## Reproduce

The complete archive includes every sufficient whole-state moment, full
selected return/poll facts, all 113 decisions, all 1,017 scenarios, code,
tests, checksums and independent rational-arithmetic verification.
It excludes respondent records and private fine cells.

```bash
python reproduce.py --output /path/to/new-directory
```
