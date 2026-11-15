import copy
import json

import pytest

from scripts import results_json_statistics as subject


def template(county, literal, native, *, identity="parent", unit=None):
    return {
        "id": identity, "election": {"year": 2026, "type": "general"},
        "geography": {
            "state_code": "IN", "name": unit or county,
            "level": "reporting_unit" if unit else "county",
        },
        "view": {
            "source_url": subject.MONROE_URL if unit or county == "Monroe County" else subject.PORTER_URL,
            "county": county, "unit": unit, "native_record": native,
        },
        "measure": {**subject.COUNT_MEASURE, "literal": literal},
        "count": {"status": "reported"},
        "denominator": None,
        "source_clock": {"literal": native.get("asOf")},
    }


def summary_fixture():
    profile = subject.PROFILES[subject.PORTER_URL]
    data = {
        "id": profile["election_id"], "jurisdictionId": profile["jurisdiction_id"],
        "electionDate": "2026-11-03",
        "name": [{"languageId": "en", "text": "2026 General Election"}],
        "dateText": [{"languageId": "en", "text": "November 3, 2026"}],
        "isProduction": True, "isPrimary": False, "isOfficialResults": False,
        "ballotsCast": 0.0, "totalVoters": 0.0, "precinctsReporting": 0.0,
        "asOf": "2026-11-04T08:07:10.0000001Z",
        "lastUpdated": "2026-11-04T08:07:09Z",
        "publishDate": "2026-11-04T08:07:11Z",
        "countGroups": [], "groupReportingStatus": [], "precinctReportingStatus": [],
    }
    return data, [template("Porter County", "ballotsCast", copy.deepcopy(data))]


def layer_fixture():
    rows = [{
        "Precinct_ID": i, "Precinct": "Literal unit " + str(i),
        "Registered_Voters": 0, "Ballots_Cast": 0, "Turnout_Percentage": None,
        "Precinct_Reporting": "Partially Reporting",
    } for i in range(1, 104)]
    data = {
        "fields": [{"name": name, "type": kind, "alias": alias}
                   for name, (kind, alias) in subject.MONROE_FIELDS.items()],
        "features": [{"attributes": copy.deepcopy(row)} for row in rows],
    }
    parent = {
        "derivation": subject.INDICATOR, "distinct_native_precincts": 103,
    }
    targets = [template("Monroe County", "Total Ballots Cast", parent)]
    targets.extend(template("Monroe County", "Native Ballots Cast", row,
                            identity=str(row["Precinct_ID"]), unit=row["Precinct"])
                   for row in rows)
    return data, targets


def parse(data, targets, url):
    return subject.statistics(json.dumps(data).encode(), targets, url)


def test_summary_refresh_retains_native_counts_status_and_full_precision_clock():
    data, targets = summary_fixture()
    data.update(
        ballotsCast=34.0, totalVoters=99.0, isOfficialResults=True,
        asOf="2026-11-04T08:07:10.0000002Z",
    )
    result = parse(data, targets, subject.PORTER_URL)
    update, = result["updates"]
    assert update["value"] == 34 and update["registered"] is None
    assert update["rate_compatible"] is False
    assert update["native"]["query"]["native_fields"]["totalVoters"] == 99.0
    assert update["native"]["query"]["source_clock"] == data["asOf"]
    assert update["native"]["source_clock_timezone_literal"] == "UTC"
    assert update["native"]["native_report_status_literal"] == "isOfficialResults=true"
    assert update["native"]["native_reporting_complete_qualified"] is False
    assert result["factual_product"]["native_json"] == data
    zero = parse(summary_fixture()[0], targets, subject.PORTER_URL)
    assert zero["updates"][0]["value"] == 0
    data.update(asOf="2026-12-01T01:00:00Z", lastUpdated="2026-12-01T00:59:59Z",
                publishDate="2026-12-01T01:00:01Z")
    assert parse(data, targets, subject.PORTER_URL)["updates"][0]["clock"].startswith("2026-12")


@pytest.mark.parametrize("key,value", [
    ("id", "other-election"), ("jurisdictionId", "other-jurisdiction"),
    ("isPrimary", True), ("isProduction", False), ("isOfficialResults", 1),
    ("electionDate", "2026-05-05"), ("name", []),
    ("ballotsCast", None), ("ballotsCast", True), ("ballotsCast", 0.5),
    ("ballotsCast", "34"), ("ballotsCast", -1), ("ballotsCast", 2**53),
    ("asOf", "2026-11-04T08:07:10Z"),
    ("lastUpdated", "2026-11-04T08:07:08Z"),
    ("publishDate", "2026-11-04T08:07:10Z"),
    ("asOf", "2026-11-04T08:07:10"), ("countGroups", {}),
])
def test_summary_rejects_changed_scope_invalid_counts_and_clock_rollback(key, value):
    data, targets = summary_fixture()
    data[key] = value
    with pytest.raises(ValueError):
        parse(data, targets, subject.PORTER_URL)


def test_distinct_indicator_refreshes_parent_and_literal_units_without_rates_or_clock():
    data, targets = layer_fixture()
    row = data["features"][0]["attributes"]
    row.update(Ballots_Cast=17, Registered_Voters=0, Turnout_Percentage=170)
    data["features"][-1]["attributes"]["Precinct_Reporting"] = "Fully Reporting"
    result = parse(data, targets, subject.MONROE_URL)
    assert len(result["updates"]) == 104 and len(result["complete_native_query"]) == 104
    parent, first = result["updates"][:2]
    assert parent["value"] == first["value"] == 17
    assert parent["native"]["native_report_status_literal"] is None
    assert parent["native"]["native_fields"]["native_precinct_reporting"] == {
        "Partially Reporting": 102, "Fully Reporting": 1,
    }
    assert first["registered"] == 0 and first["rate_compatible"] is False
    assert first["native"]["native_fields"]["Turnout_Percentage"] == 170
    assert all(row["clock"] is None and row["total_units"] is None
               and row["native"]["native_reporting_complete_qualified"] is False
               for row in result["updates"])
    assert result["updates"][-1]["value"] == 0
    assert result["factual_product"]["native_json"] == data
    for update in result["updates"]:
        target = next(row for row in targets if row["id"] == update["id"])
        target["view"]["native_record"] = update["native"]
    assert parse(data, targets, subject.MONROE_URL)["updates"] == result["updates"]


@pytest.mark.parametrize("mutation", [
    "duplicate", "omitted", "renamed", "identity", "missing", "null", "fractional",
    "boolean", "negative", "transfer", "field-role", "parent-scope", "geographic-filter",
])
def test_distinct_indicator_rejects_ambiguous_or_incomplete_inventory(mutation):
    data, targets = layer_fixture()
    row = data["features"][0]["attributes"]
    if mutation == "duplicate":
        data["features"][-1] = copy.deepcopy(data["features"][0])
    elif mutation == "omitted":
        data["features"].pop()
    elif mutation == "renamed":
        row["Precinct"] += " changed"
    elif mutation == "identity":
        row["Precinct_ID"] = 500
    elif mutation == "missing":
        del row["Ballots_Cast"]
    elif mutation == "null":
        row["Ballots_Cast"] = None
    elif mutation == "fractional":
        row["Ballots_Cast"] = 0.25
    elif mutation == "boolean":
        row["Ballots_Cast"] = False
    elif mutation == "negative":
        row["Ballots_Cast"] = -1
    elif mutation == "transfer":
        data["exceededTransferLimit"] = True
    elif mutation == "field-role":
        data["fields"][3]["alias"] = "Candidate votes"
    elif mutation == "parent-scope":
        targets[0]["view"]["native_record"]["derivation"] = "Researcher geographic sum"
    elif mutation == "geographic-filter":
        targets.pop()
    with pytest.raises(ValueError):
        parse(data, targets, subject.MONROE_URL)


def test_native_json_duplicate_and_nonfinite_values_fail_before_projection():
    data, targets = summary_fixture()
    raw = json.dumps(data).encode()
    with pytest.raises(ValueError, match="Duplicate"):
        subject.statistics(raw.replace(b'"ballotsCast": 0.0', b'"ballotsCast": 0, "ballotsCast": 1'),
                           targets, subject.PORTER_URL)
    with pytest.raises(ValueError, match="Nonfinite"):
        subject.statistics(raw.replace(b'"ballotsCast": 0.0', b'"ballotsCast": NaN'),
                           targets, subject.PORTER_URL)
