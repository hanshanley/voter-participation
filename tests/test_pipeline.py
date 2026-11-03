import csv
import hashlib
import io
import json
import zipfile

import pytest

from scripts.build import ROOT, aggregate_nc, census_data, nc_rows, normalize_key, rate_record
from scripts.download import download


def archive(tmp_path, contents):
    path = tmp_path / "source.zip"
    with zipfile.ZipFile(path, "w") as stream:
        stream.writestr("source.txt", contents)
    return path


def test_headerless_history_retains_first_row_and_leading_zero(tmp_path):
    row = "AVERY\t01  \tAge 26 - 40\tDEM\tW\tNL\tM\t5\t11/05/2002\tHistory\t2003-01-21\tV\tDEM\n"
    path = archive(tmp_path, row + row.replace("\t5\t", "\t3\t"))
    counts, total, rows = aggregate_nc(path)
    assert total == 8
    assert rows == 2
    assert counts[("AVERY", "01", "overall", "All")] == 8
    assert counts[("AVERY", "01", "race", "White")] == 8


def test_comma_delimited_2004_history_and_tab_delimited_registration(tmp_path):
    header = ["county_desc", "precinct_abbrv", "age", "party_cd", "race_code",
              "ethnic_code", "sex_code", "total_voters"]
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerow(["WAKE", "01-01", "Age 18 - 25", "UNA", "B", "NL", "F", "7"])
    path = archive(tmp_path, stream.getvalue())
    counts, total, _ = aggregate_nc(path)
    assert total == 7
    assert counts[("WAKE", "01-01", "sex", "Female")] == 7
    assert list(nc_rows(archive(tmp_path, "\t".join(header) + "\n"
                                + "\t".join(["WAKE", "01-01", "Age 18 - 25", "UNA", "B", "NL", "F", "7"]) + "\n")))[0]["total_voters"] == "7"


def test_unavailable_archive_is_not_zero_turnout(tmp_path):
    with pytest.raises(ValueError, match="no unique tabular"):
        list(nc_rows(archive(tmp_path, "Data Unavailable")))


def test_invalid_rates_preserve_counts_without_clipping():
    assert rate_record(11, 10)["turnout_pct"] is None
    assert rate_record(11, 10)["participants"] == 11
    assert "participation_exceeds_registration" in rate_record(11, 10)["quality"]
    assert rate_record(5, 0)["turnout_pct"] is None
    assert rate_record(0, 10, False)["participants"] is None
    assert rate_record(0, 10, False)["turnout_pct"] is None
    assert rate_record(0, 10)["turnout_pct"] == 0


def test_source_population_bases_are_never_silently_substituted(tmp_path, monkeypatch):
    import scripts.build as module
    monkeypatch.setattr(module, "OUT", tmp_path)
    national, states = census_data()
    assert {r["denominator"] for r in national if r["dimension"] == "education"} == {"vap"}
    assert {r["denominator"] for r in national if r["dimension"] == "sex"} == {"vap"}
    assert any(r["denominator"] == "cvap" and r["year"] == 2022 and r["dimension"] == "race"
               for r in national)
    assert any(r["denominator"] == "cvap" and r["year"] == 2006 for r in states)
    assert len({(r["year"], r["age_group"], r["dimension"], r["group"], r["denominator"])
                for r in national}) == len(national)


def test_negative_counts_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="Negative count"):
        aggregate_nc(archive(tmp_path, "WAKE\t01\tAge 26 - 40\tUNA\tW\tNL\tM\t-1\t11/05/2002\tHistory\tdate\tV\tUNA\n"))


def test_source_nul_placeholders_are_removed_and_audited(tmp_path):
    audit = {}
    path = archive(tmp_path, "WAKE\t01\tAge 26 - 40\tUNA\tW\tNL\tM\t5\t11/05/2002\tHistory\tdate\tV\t\x00\n")
    _, total, rows = aggregate_nc(path, audit)
    assert (total, rows) == (5, 1)
    assert audit["nul_bytes_removed"] == 1


def test_cached_source_checksum_is_verified_without_network(tmp_path, monkeypatch):
    import scripts.download as module
    monkeypatch.setattr(module, "ROOT", tmp_path)
    path = tmp_path / "file.txt"
    path.write_text("original")
    spec = {"path": "file.txt", "url": "https://example.invalid", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    monkeypatch.setattr(module.requests, "get", lambda *a, **k: pytest.fail("Verified cache must not use network"))
    assert download(spec)["status"] == "cached"


def test_completed_data_reconcile_and_all_downloads_are_complete():
    path = ROOT / "public/data/analysis.json"
    if not path.exists():
        pytest.skip("Run the data build before the artifact integration check")
    report = json.loads(path.read_text())
    for summary in report["nc_summaries"]:
        if summary["status"] != "aggregated":
            continue
        data = json.loads((ROOT / f"public/data/nc/{summary['year']}.json").read_text())
        overall = [r for r in data["records"] if r["dimension"] == "overall"]
        assert sum(r["participants"] or 0 for r in overall) == summary["participants"]
        assert sum(r["registered"] for r in overall) == summary["registered"]
        for r in data["records"]:
            if r["turnout_pct"] is not None:
                assert 0 <= r["turnout_pct"] <= 100
    with zipfile.ZipFile(ROOT / "public/data/complete-analysis.zip") as archive_file:
        assert "national.csv" in archive_file.namelist()
        assert "nc/2024.csv" in archive_file.namelist()
        assert "nc/2004.csv" in archive_file.namelist()
        assert "coverage.csv" in archive_file.namelist()
