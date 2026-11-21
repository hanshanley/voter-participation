from datetime import datetime, timezone
from copy import deepcopy
from unittest.mock import patch

from scripts import north_carolina_participation as nc, results_intake as intake


def test_published_age_control_rejects_a_one_credit_difference_and_wrong_denominator():
    assert nc.reviewed_age_rate(629299, 1841623, [629298, 342]) == (None, "published_history_count_differs")
    assert nc.reviewed_age_rate(233441, 900000, [233441, 241]) == (None, "published_age_rate_differs")
    assert nc.reviewed_age_rate(233441, 968290, [233441, 241]) == (23344100 / 968290, None)


def test_paired_bulk_capture_accepts_both_revision_directions_and_retains_on_failure(tmp_path):
    feed = "NC-2016-general-participation-statistics"
    election = nc.FEEDS[feed]
    endpoints = {kind: nc.report_url(kind, election) for kind in nc.CATALOGS}
    bodies = {catalog: f'<a href="{endpoints[kind]}">Election archive</a>'.encode()
              for kind, catalog in nc.CATALOGS.items()} | {
                  endpoints["history"]: b"100", endpoints["voter"]: b"150"}

    def acquire(_, spec, *, access_guard):
        body = bodies[spec["url"]]
        return body, {"origin": "fixture", **intake.pin(body)}

    def extract(body, kind, day):
        return {"edition": "2016-12-28", "count": int(body)}

    with patch.object(intake.Store, "acquire", acquire), patch.object(nc, "extract", extract):
        def capture(prior=None):
            collector = intake.Collector(tmp_path, {feed: prior} if prior else {},
                                         {"urls": [], "prefixes": [], "hosts": []},
                                         datetime(2026, 11, 21, tzinfo=timezone.utc))
            return nc.collect(collector, feed)

        first = capture()
        assert first["status"] == "reported"
        assert capture(first) == first
        bodies[endpoints["history"]] = b"103"
        up = capture(first)
        assert up["data"]["pair"]["history"]["facts"]["count"] == 103
        bodies[endpoints["history"]] = b"97"
        down = capture(up)
        assert down["data"]["pair"]["history"]["facts"]["count"] == 97
        old = deepcopy(down)
        bodies[nc.CATALOGS["voter"]] = b"<html>No archive link</html>"
        retained = capture(down)
        assert retained["status"] == "retained_after_failure"
        assert retained["error"] == "report_not_linked"
        assert retained["data"] == old["data"]
