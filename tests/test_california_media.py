from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from scripts import california_media as ca, results_intake as intake


def transmission(kind, rows, timestamp="0001000"):
    fields = [f"[B|CAS|1|20261121|{timestamp}]"]
    fields.extend(f"[{kind}|CAS|{i}|{'|'.join(row)}]" for i, row in enumerate(rows, 2))
    fields.append(f"[E|CAS|{len(rows) + 2}|20261121|{timestamp}]")
    return ("\r\n".join(fields) + "\r\n").encode()


def vote_file(n, clock="0001000"):
    counties = [[str(i), "U", "0", "0", "1", "1", "100", str(n), "100", str(n),
                 "202611032001", "202611201825"] for i in range(1, 59)]
    counties.append(["59", "F", "0", "0", "58", "58", "100", str(58 * n), "5800", str(n),
                     "202611032001", "202611201826"])
    return transmission("A", counties, clock) + transmission(
        "V", [["110000010000", "59", "1", "1", "F", "12", "9", "100", "100"]], clock)


def test_turnout_refresh_accepts_revisions_and_retains_last_good(tmp_path):
    bodies = {
        ca.INDEX: b"<title>November 3, 2026, California General Election Results</title>" + b"".join(
            f'<a href="{url}">{kind}</a>'.encode() for kind, url in ca.URLS.items()),
        ca.URLS["S"]: transmission("S", [[f"{i:02}", name]
            for i, name in enumerate([*ca.CA_COUNTIES, "State of California"], 1)]),
        ca.URLS["V"]: vote_file(50),
    }

    def acquire(_, spec, *, access_guard):
        body = bodies[spec["url"]]
        return body, {"origin": "fixture", **intake.pin(body)}

    def capture(old=None):
        return ca.collect(intake.Collector(tmp_path, {ca.TURNOUT: old} if old else {},
                          {"hosts": [], "prefixes": [], "urls": []},
                          datetime(2026, 11, 21, 12, tzinfo=timezone.utc)), ca.TURNOUT)

    with patch.object(intake.Store, "acquire", acquire):
        first = capture()
        assert first["status"] == "reported"
        assert capture(first) == first
        bodies[ca.URLS["V"]] = vote_file(52, "0002000")
        up = capture(first)
        assert ca.exports({ca.TURNOUT: up})[0][-1]["reported_ballots_cast"] == 3016
        bodies[ca.URLS["V"]] = vote_file(49, "0003000")
        down = capture(up)
        assert ca.exports({ca.TURNOUT: down})[0][-1]["reported_ballots_cast"] == 2842
        for bad in (vote_file(51), vote_file(49, "0004000").replace(b"|2842|5800|49|", b"|2843|5800|49|"),
                    vote_file(49, "0004000").replace(b"[A|CAS|17|", b"[A|CAS|18|")):
            bodies[ca.URLS["V"]] = bad
            retained = capture(down)
            assert retained["status"] == "retained_after_failure"
            assert retained["data"] == down["data"]


def test_house_returns_do_not_impute_missing_candidates_or_unlock_model():
    code = "110000010000"
    offices = {code: "United States Representative District 1"}
    candidates = {code: {"12": {"candidate_name": "Candidate A"}, "13": {"candidate_name": "Candidate B"}}}
    data = {"house": [
        [code, "59", "1", "1", "F", "12", "9", "100", "90", "13", "1", "100", "10"],
        [code, "1", "1", "1", "U", "12", "9", "100", "90", "13", "1", "100", "10"],
    ]}
    rows = list(ca.house_rows(data, offices, candidates))
    assert all(r["listed_vote_counts_reconcile"] and not r["exhaustive_write_in_universe_verified"] for r in rows)
    partial = deepcopy(data)
    del partial["house"][1][-4:]
    rows = list(ca.house_rows(partial, offices, candidates))
    assert all(not r["listed_vote_counts_reconcile"] for r in rows)
    assert [r["votes"] for r in rows if r["county_code"] == 1 and r["candidate_id"] == "13"] == [None]
    with pytest.raises(ValueError, match="Unknown or duplicate"):
        list(ca.house_rows({"house": [data["house"][0] + ["14", "1", "100", "10"]]}, offices, candidates))
