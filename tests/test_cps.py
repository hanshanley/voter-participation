import csv
import hashlib
import io
import json
import zipfile

import pytest

from scripts.cps import LAYOUT, ROOT, YEARS, aggregate, compare, export, records


def person(**changes):
    return {"month": 11, "year": 2024, "state": 37, "age": 30, "sex": 2,
            "education": 43, "race": 1, "hispanic": 2, "person_type": 2,
            "citizenship": 1, "weight": 10000, "interview": 1, "voted": 1, **changes}


def test_joint_cells_preserve_unknowns_weights_and_civilian_citizen_universe():
    rows = [person(), person(voted=2, weight=30000),
            person(interview=2, voted=-1, weight=60000),
            person(voted=-2), person(voted=-3), person(voted=-9),
            person(age=17), person(citizenship=5), person(person_type=3)]
    result = aggregate(rows, 2024)
    summary = result["summary"]
    assert summary["sample_n"] == 6
    assert summary["citizens_weighted"] == 13
    assert summary["reported_voters_weighted"] == 1
    assert summary["reported_nonvoters_weighted"] == 3
    assert summary["unknown_weighted"] == 9
    assert summary["reported_voting_pct"] == pytest.approx(100 / 13)
    assert summary["respondent_only_voting_pct"] == 25
    assert summary["missing_outcome_upper_pct"] == pytest.approx(1000 / 13)
    assert summary["supplement_noninterview_n"] == 1
    assert summary["dont_know_n"] == summary["refused_n"] == summary["no_response_n"] == 1
    assert summary["weight_only_effective_n"] == pytest.approx(169 / 49)
    assert result["audit"]["outside_universe"] == 3
    assert result["joint_cells"][0]["citizens_weighted"] == 13


def test_joint_race_ethnicity_is_exclusive_but_published_race_marginals_overlap():
    result = aggregate([person(), person(hispanic=1), person(race=2)], 2024)
    joint = result["joint_cells"]
    assert {row["race_ethnicity"] for row in joint} == {
        "White, non-Hispanic", "Hispanic, any race", "Black, non-Hispanic"}
    assert sum(row["sample_n"] for row in joint) == 3
    race = {r["group"]: r["sample_n"] for r in result["marginals"] if r["dimension"] == "race"}
    assert race == {"White": 2, "Black": 1, "White, non-Hispanic": 1, "Hispanic, any race": 1}
    for dimension in ("age", "sex", "education", "race_ethnicity", "state"):
        assert sum(r["sample_n"] for r in result["marginals"] if r["dimension"] == dimension) == 3


@pytest.mark.parametrize("changes", [
    {"weight": -1}, {"interview": 2, "voted": 1}, {"voted": 0},
    {"state": 99}, {"hispanic": -1}, {"education": 99},
])
def test_invalid_inputs_cannot_be_silently_recoded(changes):
    with pytest.raises(ValueError):
        aggregate([person(**changes)], 2024)


@pytest.mark.parametrize("bad", ["short", "wrong_year", "wrong_month"])
def test_fixed_width_reader_rejects_malformed_or_wrong_election_inputs(tmp_path, bad):
    row = person(**({"year": 2022} if bad == "wrong_year" else {"month": 10} if bad == "wrong_month" else {}))
    line = bytearray(b" " * 1020)
    for field, (start, end) in LAYOUT.items():
        line[start - 1:end] = str(row[field]).rjust(end - start + 1).encode()
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("nov24pub.dat", bytes(line[:1000] if bad == "short" else line) + b"\r\n")
    with pytest.raises(ValueError):
        list(records(path, 2024))


def test_source_corruption_stops_export_before_promoting_results(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "source.zip").write_bytes(b"changed")
    (tmp_path / "data/cps-sources.json").write_text(json.dumps({
        "sources": [{"path": "source.zip", "bytes": 7, "sha256": "wrong"}]}))
    with pytest.raises(ValueError, match="checksum mismatch"):
        export(tmp_path, rebundle=False)
    assert not (tmp_path / "public/data/cps/inputs.json").exists()


def test_published_comparisons_require_both_elections_and_report_discrepancies():
    published = [{"year": year, "denominator": "cvap", "dimension": "overall",
                  "group": "All", "age_group": "All ages", "turnout_pct": 50,
                  "source": "official.xlsx", "source_row": 1} for year in YEARS]
    marginal = [{"year": year, "dimension": "overall", "group": "All",
                 "reported_voting_pct": 60} for year in YEARS]
    result = compare(marginal, published)
    assert all(not row["passed"] and row["difference_pp"] == 10 for row in result)
    with pytest.raises(ValueError, match="required year"):
        compare(marginal, published[:1])


def test_real_cps_exports_reconcile_and_include_all_observations_and_originals():
    folder = ROOT / "public/data/cps"
    result = json.loads((folder / "inputs.json").read_text())
    with zipfile.ZipFile(folder / "complete-inputs.zip") as archive:
        assert json.loads(archive.read("inputs.json")) == result
        joint = list(csv.DictReader(io.StringIO(archive.read("joint-cells.csv").decode())))
        for source in result["source_manifest"]["sources"]:
            raw = archive.read(source["path"])
            assert hashlib.sha256(raw).hexdigest() == source["sha256"]
        replayed_marginals = []
        for summary in result["summaries"]:
            year = summary["year"]
            original = ROOT / f"data/raw/cps/{year}/nov{year % 100}pub.zip"
            replay = aggregate(records(original, year), year)
            replayed_marginals.extend(replay["marginals"])
            assert replay["summary"]["reported_voting_pct"] == summary["reported_voting_pct"]
            cells = [r for r in joint if int(r["year"]) == year]
            assert len(cells) == summary["observed_joint_cells"]
            assert sum(int(r["sample_n"]) for r in cells) == summary["sample_n"]
            assert sum(float(r["citizens_weighted"]) for r in cells) == pytest.approx(summary["citizens_weighted"])
        published = json.loads(archive.read("inputs/national.json"))
        assert compare(replayed_marginals, published) == result["comparisons"]
    assert result["published_comparisons_passed"]
    assert result["release_2026_allowed"] is False
