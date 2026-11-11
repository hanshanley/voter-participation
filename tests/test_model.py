import hashlib
import json
import zipfile

import pytest

from scripts.model import ROOT, analyze, backtest, export, logit


def observations():
    rows = []
    for year in range(2000, 2025, 2):
        election = "presidential" if year % 4 == 0 else "midterm"
        total = 60 if election == "presidential" else 45
        for dimension, group, rate in [("overall", "All", total), ("sex", "Female", total + 5)]:
            rows.append({"year": year, "election_type": election, "dimension": dimension,
                         "group": group, "age_group": "All ages", "denominator": "cvap",
                         "turnout_pct": rate, "source": "public.xlsx", "source_row": year})
    return rows


def test_held_out_targets_and_future_elections_cannot_leak_into_predictions():
    rows = observations()
    original = next(row for row in backtest(rows) if row["year"] == 2014)
    for row in rows:
        if row["year"] >= 2014:
            row["turnout_pct"] = 90
    changed = next(row for row in backtest(rows) if row["year"] == 2014)
    assert changed["predicted_pct"] == original["predicted_pct"]
    assert changed["baseline_pct"] == original["baseline_pct"]
    assert changed["observed_cps_pct"] != original["observed_cps_pct"]
    assert changed["national_input_year"] == 2010
    assert changed["training_years"] == [2002, 2006, 2010]


def test_presidential_and_midterm_training_and_population_bases_stay_separate():
    rows = observations()
    rows += [{**row, "denominator": "vap", "turnout_pct": 5} for row in rows]
    tests = backtest(rows)
    for row in tests:
        assert all(year < row["year"] and year % 4 == row["year"] % 4
                   for year in row["training_years"])
        assert row["baseline_pct"] == (65 if row["election_type"] == "presidential" else 50)
        assert row["denominator"] == "cvap"
    missing = [row for row in rows if row["year"] != 2010]
    assert not any(row["year"] == 2014 for row in backtest(missing))


@pytest.mark.parametrize("rate", [0, 100, -1, float("nan"), True])
def test_invalid_rates_cannot_be_clipped_into_model_inputs(rate):
    with pytest.raises(ValueError):
        logit(rate)


def test_real_historical_tests_never_authorize_unvalidated_2026_estimates():
    rows = json.loads((ROOT / "public/data/national.json").read_text())
    result = analyze(rows)
    assert result["predictions"]
    assert {row["dimension"] for row in result["predictions"]} == {"age", "race", "sex", "education"}
    assert all(max(row["training_years"]) < row["year"] <= 2024 for row in result["predictions"])
    assert all(min(row["training_years"]) >= 2004 for row in result["predictions"] if row["dimension"] == "race")
    assert result["estimates_2026"] == []
    assert result["release_2026"]["allowed"] is False
    assert result["summary"]["model_mae_pp"] == pytest.approx(
        sum(row["absolute_error_pp"] for row in result["predictions"]) / len(result["predictions"]))


def test_complete_validation_export_contains_every_prediction_input_and_method(tmp_path):
    data = tmp_path / "public/data"
    data.mkdir(parents=True)
    raw = json.dumps(observations()).encode()
    (data / "national.json").write_bytes(raw)
    (data / "sources.json").write_text("{}")
    (tmp_path / "METHODOLOGY.md").write_text("Independent method")
    result = export(tmp_path, rebundle=False)
    assert result["input"]["sha256"] == hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(data / "model/complete-validation.zip") as archive:
        assert archive.read("inputs/national.json") == raw
        assert json.loads(archive.read("validation.json")) == result
        assert len(archive.read("backtests.csv").decode().splitlines()) == len(result["predictions"]) + 1
        assert archive.read("METHODOLOGY.md") == b"Independent method"
