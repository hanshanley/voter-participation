Whole-state 2024-to-2026 House switching/no-counted-ballot transition estimates for all 50 states.
These are conditional modeled flows, not linked voter histories or causal evidence of persuasion.
Both years retain their reported House categories and UF ballot/VEP benchmarks.
H includes ballots without a reported House choice, including unreported uncontested choices; H is not staying home.
N means no counted ballot in the assumed eligible accounting frame, not proof someone physically stayed home.
E separates eligibility/frame change. State model counts are not additive unique people.
Percentages use all 2024 recorded House D/R/Other-unassigned votes; contributions use Democratic D/(D+R) points.
The complete case file contains all 109350 decisions and every feasible 6-by-6 matrix, including rejected hypothetical ballot cases.
Ranges are assumption sensitivity, not confidence intervals or complete source/population uncertainty.
UF benchmarks: Michael McDonald, University of Florida Election Lab, 2024 v0.4 and 2026 v0.3; CC-BY-4.0.
No private respondents or private fine source cells are redistributed.
For byte-identical replay use CPython 3.12:
python -m scripts.statewide_house_transitions --inputs inputs --output reproduced
python -m scripts.verify_statewide_house_transitions --inputs inputs --product reproduced
python -m unittest discover -s tests -p test_statewide_house_transitions.py
