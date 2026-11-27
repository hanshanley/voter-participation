Outcome audit, not a refit or a validation of individual histories.
All 50 state queries, all 435 selected native contests and all statewide turnout-frame decisions.
Includes the complete captured public inputs, source receipts, code and tests. No private survey records.
python3 -m scripts.audit_source_estimates --inputs inputs --output reproduced
python3 -m unittest discover -s tests -p test_audit_source_estimates.py
