# Recorded House totals and model eligibility

The reported-count view and behavioral model answer different questions.
Known recorded counts should remain inspectable even when an election comparison
cannot support a switching/nonparticipation explanation.

The explorer defaults to **Democratic two-party-share points**. Texas's held
2024 D/R counts are 4,310,913 / 6,234,918; the held 2026 counts are
5,147,146 / 4,591,278. They imply **+11.97610548 Democratic-share points**, or
**+23.95221096 D-minus-R margin points**. Gray in the comparable/model view means
unavailable, not a Republican result. Texas's recorded totals remain available
in its state details, the separate unadjusted recorded-count view and the complete
50-state table/download.

For each year:

```text
Democratic two-party share = 100 * D / (D + R)
D-minus-R margin = 100 * (D - R) / (D + R)
margin change = 2 * Democratic two-party-share change
```

Other-party votes are preserved but outside this denominator. These are not
population turnout rates. Switching/entry/exit contributions have their own
model assumptions and must not be inferred simply from a net vote-share change.

## What remains held

The separate recorded-count view is explicitly **unadjusted**. Changed
major-party candidate coverage, unopposed contests, omitted counts, reporting
stages and coalition labels can distort comparisons of literal party totals.
Alaska and Massachusetts's negative raw changes must not be promoted into
Republican voter-preference swings. They are retained for transparent source
inspection, not forced positive or used as behavioral targets.

The accepted **33 conditional / 17 held** model decisions, source fits, weights,
group masks and complete simulation outputs are unchanged. No source-only
scenario is substituted for a held election explanation.

## Complete numerical reproduction

The [complete packet](https://github.com/hanshanley/margin_of_error/releases/download/participation-house-recorded-counts-20261113-01/complete-analysis.zip)
contains every recorded state/count/share/change/eligibility query, exact
processing and interface code, all 37 focused tests and their sufficient fixtures,
and the **entire preceding 50,449,445-byte scientific packet**. It is not a
metadata-only inventory or a sample of the model outputs.

From the extracted `code/` directory:

```sh
node --test scripts/participation-return-drivers.test.mjs \
  scripts/participation-transition-scenarios.test.mjs \
  scripts/participation-calibrated-swing.test.mjs \
  scripts/participation-norc-house.test.mjs
```

`REPRODUCE.txt` gives the exact input SHA and the
`scripts/export-house-recorded-counts.mjs` command. Compare both exported JSON
and CSV with `queries/`. Every recorded count is checked against the accepted
all-district audit, and vote shares/changes are independently checked with exact
rational arithmetic. Two fresh offline extractions pass all 37 tests and
reproduce both complete numerical outputs byte-for-byte, with network, DNS and
child commands blocked and probed.

This correction still uses the explicitly held **November 7, 2026** source
snapshot; it is not a fresh native-return or NORC-weight update. The newer
official Hawaii/Wyoming originals and the NORC version/weight review remain
separate work in [REMAINING.md](../REMAINING.md). No source refit or wholesale
predecessor resimulation is claimed.
