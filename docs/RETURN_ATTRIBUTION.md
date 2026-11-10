# 2026 modeled margin contributions

## Reported-swing correction: version 20261110-02

The primary maps now distinguish the **reported same-office swing** from
modeled switching, modeled nonparticipation, and **other / unallocated**.
The three contribution maps add to the reported total wherever a qualified
historical comparison exists. All margins use `100 * (D - R) / (D + R)`.

All original 113 models and their sensitivity ranges remain unchanged.
Their seven terms explain a recalled-presidential survey-frame contrast,
not the observed earlier same-office margin. An eighth, explicitly unallocated
baseline-alignment term closes that difference without fitting earlier
partisan composition or calling the residual persuasion or staying home.

For example, the held Texas House counts imply **+25.16363563924734 pp**:
switching **+3.5983884082676587**, modeled nonparticipation
**-0.8468238317922675**, and other/unallocated **+22.41207106277195**.
The new baseline alignment alone is **+14.62083777048145 pp**.

There are 89 qualified comparisons: 35 House aggregates, 26 Senate races and
28 supplied governor frames. Missing comparisons remain unavailable; the
original conditional components are not hidden or relabelled as totals.
House requires exact Census county identities, known prior/current counts
and agreement with complete held current candidate controls. Competition
screens remain qualifications, not reasons to discard actual recorded votes.
Senate uses the FEC 2020 regular-seat results, with Georgia's full-term
January 2021 runoff separate from its other seat. Minnesota DFL is an explicit
party-code alias; independent/fusion/unmapped affiliations remain Other.
Unresolved more recent specials, missing prior seats and unqualified party
pairs are withheld. Governor comparisons retain their supplied matched
2022/2026 county frames and are not certified complete statewide results.

The new complete packet contains both entire predecessor analysis packets,
the full FEC workbook, the full Census Gazetteer original, inputs, code, tests,
queries and hashes. Its offline reproduction rebuilds both predecessor
analyses and byte-compares every new comparison. Prior immutable numerical
versions and complete downloads remain intact.

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
