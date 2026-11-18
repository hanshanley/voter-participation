# Direct statewide ballot totals

The hourly analytical runtime checks reviewed statewide administrative ballot
parents separately from candidate returns. Its first profile uses Wyoming's
retained official statewide workbook: `Statewide Total Ballots Cast`, cell B28,
reconciled against all 23 county parents.

The initial observation is 191,713 ballots. This is retained evidence newly
connected to the canonical participation display, not a new source acquisition,
candidate-vote sum, turnout rate, unique-voter count or local allocation.
The source supplies no matched denominator or native count-update clock here.
The filename's `OFFICIAL` label is not separate certification evidence.

`scripts/statewide_ballot_totals.py` validates the complete source facts and
original pin on each update. Its one-time reviewed inventory addition retains
all existing Wyoming observations and view selections. Subsequent compatible
upward and downward revisions update the stable canonical observation, statewide
display mirror and both complete query exports automatically. A source failure
retains the last good count and its evidence, marks it retained, and never
creates a new observation without a qualified source.

The existing runtime command is unchanged:

```sh
python -m scripts.automatic_runtime --help
python -m pytest -q tests/test_statewide_ballot_totals.py
```

The complete runtime download includes the original source packet, all numerical
inputs, accepted preceding rolling seed, code and tests. Its `REPRODUCE.txt`
contains the exact network-free reproduction command. The new complete exports
are:

```text
participation/native-statewide-ballot-totals.csv
participation/native-statewide-ballot-totals.json.gz
```

House and Senate comparison/model eligibility, all existing native geographic
layers and all historical scientific versions remain separate and unchanged.
