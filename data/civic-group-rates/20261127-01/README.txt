Rounded native 2026 LIKELYVOTER shares; not observed completed turnout.
All 1,530 queries, including unavailable categories; no new subgroup counts or weights.
Original private respondent data are deliberately not redistributed.
To independently repeat the source reduction, use the user-supplied civichealth_datafile.csv
with SHA256 496a5b57fbc435210bdf78e2c1c3717879c0689c74081bee830d121b548c792f. No other file is silently substituted.
python3 -m scripts.civic_group_rates --source /private/civichealth_datafile.csv --reference inputs/previous-public-query.json --output reproduced
python3 -m scripts.verify_civic_group_rates --source /private/civichealth_datafile.csv --product reproduced
python3 -m unittest discover -s tests -p test_civic_group_rates.py
