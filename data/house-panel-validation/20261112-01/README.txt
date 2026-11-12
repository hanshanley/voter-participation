Conditional same-office House source concordance, 2022 to 2024

This full packet contains all permitted sufficient inputs, all 319 public query
decisions (2 available tables and 317 whole-table holds), 8 coarse source cells,
five complete numerical outputs, exact source/code/test pins and native checks.
No raw respondents, identifiers, native fine cells or trained models are included.
The two coding records are code/citation evidence only: inherited native-release
and population-validation holds are not overridden by including those records.

CES: retained 2020-adult panel, 2022 and 2024 post-election House reports;
positive administrative participation histories at both waves, known D/R choices,
positive commonpostweight_24. Choices require conditional shared-item code transport,
not panel-native numeric labels. Missing/contradictory histories remain separate.
AP: positive POLLCLOSE_STATE_WEIGHT, modeled current voter, known actual recalled
House22/current House24 source responses. Recalled22 codes1R/2D are reversed;
QVOTE2022S is forbidden. This is not the final-vote weight frame of the fitted bridge.
Pooled state-weight cases are not a national population-weighted estimate.
Different recruitment, retention, recall, answer timing, state and administrative
frames prevent interpreting differences as recall bias or population/model error.
Each source rate is conditional on both choices being D/R, not all prior voters.
This does not validate entry, staying home, first-ever voting, 2026 state behavior
or precinct allocations, change the accepted three models, or provide design CIs.

Standard-library-only offline public numerical replay (no private extraction):
python -S -W error code/scripts/reproduce_house_panel_validation.py --archive COMPLETE_ZIP --output NEW_DIRECTORY
Native extraction can be audited separately with the pinned original sources,
the two exact coding records and code/scripts/house_panel_validation.py --help.
Private-source arithmetic was independently checked with SQL and exact fractions.
Source code commit: b97cb7ff535d39b8853e84f98944e31e332328df
