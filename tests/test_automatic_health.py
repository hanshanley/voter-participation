from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from urllib.error import HTTPError

import pytest

from scripts import automatic_health as health


@pytest.mark.parametrize("http_status,reason,headers,exit_code", [
    (403, "rate limit exceeded", {}, 75),
    (429, "Too Many Requests", {"Retry-After": "120"}, 75),
    (403, "Forbidden", {}, None),
])
def test_monitor_reports_rate_limit_without_retry_or_issue_edits(
        tmp_path, monkeypatch, capsys, http_status, reason, headers, exit_code):
    import json
    import sys
    from urllib.error import HTTPError

    calls = []

    def unavailable(request, *, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, http_status, reason, headers, None)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)

    summary = tmp_path / "summary"
    monkeypatch.setattr(health, "urlopen", unavailable)
    monkeypatch.setattr(health, "datetime", FixedClock)
    monkeypatch.setattr(sys, "argv", ["automatic_health", "--update-issue"])
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    if exit_code:
        with pytest.raises(SystemExit) as exc:
            health.main()
        assert exc.value.code == exit_code
        assert json.loads(capsys.readouterr().out) == {
            "status": "monitoring_unavailable", "reason": "github_api_rate_limited",
            "issue_action": "unchanged",
        }
        assert "monitoring_unavailable" in summary.read_text()
    else:
        with pytest.raises(HTTPError):
            health.main()
        assert not summary.exists()
    assert len(calls) == 1


NOW = datetime(2026, 11, 18, 19, tzinfo=timezone.utc)


def downloadable_runtime(active):
    tag = "automatic-participation-" + active["version"]
    url = f"https://github.com/{health.WEBSITE}/releases/download/{tag}/complete-analysis.zip"
    active["complete_download"] = {
        "url": url, "bytes": 234, "sha256": "a" * 64, "verified_anonymously": True,
    }
    return f"repos/{health.WEBSITE}/releases/tags/{tag}", {
        "draft": False, "tag_name": tag, "assets": [{
            "name": "complete-analysis.zip", "state": "uploaded", "browser_download_url": url,
            "size": 234, "digest": "sha256:" + "a" * 64,
        }],
    }


@pytest.mark.parametrize(("problem", "status"), [
    ("missing_release", "release_not_public"),
    ("draft", "release_not_public"),
    ("missing_asset", "missing_or_duplicate_complete_zip"),
    ("changed_digest", "complete_zip_differs_from_manifest"),
    (None, "verified"),
])
def test_complete_download_checks_anonymous_release_and_exact_asset(problem, status):
    active = {"version": "c" * 64}
    endpoint, release = downloadable_runtime(active)
    if problem == "draft":
        release["draft"] = True
    elif problem == "missing_asset":
        release["assets"] = []
    elif problem == "changed_digest":
        release["assets"][0]["digest"] = "sha256:" + "d" * 64

    def request(path):
        assert path == endpoint
        if problem == "missing_release":
            raise HTTPError(path, 404, "Not found", {}, None)
        return release

    assert health.complete_download_status(active, request) == status


def test_matching_future_dated_versions_are_not_healthy():
    observed = (NOW + timedelta(seconds=1)).isoformat()
    source = {"version": "a" * 64, "checked_at": observed}
    active = {"version": "b" * 64, "input_results_version": source["version"], "checked_at": observed}
    assert set(health.assess(NOW, {}, source, active)["persistent_problems"]) == {"clock"}


def previous(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


def run(run_id, hours, conclusion="success"):
    return {"id": run_id, "status": "completed", "conclusion": conclusion,
            "created_at": previous(hours), "updated_at": previous(hours)}


def report(collection, publication, *, caught_up=True, age=2.5):
    source = {"version": "a" * 64, "checked_at": previous(age)}
    active = {"version": "c" * 64, "checked_at": previous(age),
              "input_results_version": ("a" if caught_up else "b") * 64}
    return health.assess(NOW, {"collection": collection, "publication": publication}, source, active)


def test_unchanged_sources_and_normal_holds_are_not_missed_runs():
    healthy = report([run(4, 0.5)], [run(5, 0.25)], age=48)
    assert healthy["caught_up"] and not healthy["persistent_problems"]
    assert healthy["source"]["collection_checked_at"] == previous(48)
    assert healthy["scheduled_writers"]["collection"]["last_success_id"] == 4


def test_alerts_distinguish_missed_runs_repeated_failures_and_stuck_revision():
    problems = report([run(1, 4)], [run(3, 0.2, "failure"), run(2, 1, "cancelled")],
                      caught_up=False)["persistent_problems"]
    assert set(problems) == {"collection", "publication", "handoff"}
    assert "repeated" in problems["publication"]
    assert not report([run(1, 0.5)], [run(3, 0.1, "failure"), run(2, 1)],
                      caught_up=False, age=1)["persistent_problems"]


def test_issue_lifecycle_deduplicates_and_waits_for_recovery():
    issues = [{"number": 7, "title": health.TITLE, "body": "Manual report",
               "user": {"login": "maintainer"}, "state": "open"}]
    writes = []

    def request(path, method="GET", body=None):
        if method == "GET":
            return [issue for issue in issues if issue["state"] == "open"]
        writes.append((method, path, body))
        if method == "POST":
            issues.append({**body, "number": 8, "state": "open",
                           "user": {"login": "github-actions[bot]"}})
        else:
            assert path.endswith("/8")
            issues[-1].update(body)

    stalled = report([run(1, 4)], [run(2, 0.5)], caught_up=False)
    assert health.update_issue(stalled, request) == "opened"
    assert health.update_issue(stalled, request) == "unchanged"
    assert health.update_issue(report([run(4, 0.5)], [run(5, 0.5)], caught_up=False),
                               request) == "updated"
    assert health.update_issue(report([run(4, 0.5)], [run(5, 0.5)], caught_up=False, age=0.25),
                               request) == "unchanged"
    assert health.update_issue(report([run(4, 0.5)], [run(6, 0.25)]), request) == "closed"
    assert [item[0] for item in writes] == ["POST", "PATCH", "PATCH"]
    assert issues[0]["state"] == "open"


def test_outside_election_window_does_not_query_or_write():
    def unexpected(*args, **kwargs):
        raise AssertionError("Unexpected GitHub request")

    assert health.check(datetime(2026, 11, 2, tzinfo=timezone.utc), unexpected,
                        write_issue=True) == {"status": "outside_collection_window"}


def test_fresh_arrival_does_not_hide_unconsumed_predecessor_or_catalog_drift():
    source_ref, runtime_ref, cutoff_ref = "1" * 40, "2" * 40, "3" * 40
    source = {"version": "a" * 64, "checked_at": previous(0.5)}
    active = {"version": "c" * 64, "input_results_version": "b" * 64,
              "checked_at": previous(4), "counts": {"version": "count"},
              "native": {"version": "native"}}
    old = {"version": "d" * 64, "checked_at": previous(2.5)}
    catalog = {"datasets": {"participation-counts-2026": active["counts"],
                            "participation-native-bindings-2026": {"version": "different"}}}
    release_path, release = downloadable_runtime(active)

    def request(path, raw=False):
        source_root = f"repos/{health.SOURCE}"
        website_root = f"repos/{health.WEBSITE}"
        if "/actions/" in path:
            return {"workflow_runs": [run(1, 0.25)]}
        return {
            f"{source_root}/git/ref/tags/results-data":
                {"object": {"type": "commit", "sha": source_ref}},
            f"{website_root}/git/ref/tags/participation-data":
                {"object": {"type": "commit", "sha": runtime_ref}},
            f"{source_root}/contents/latest.json?ref={source_ref}": source,
            f"{website_root}/contents/automatic/latest.json?ref={runtime_ref}": active,
            f"{website_root}/contents/catalog.json?ref={runtime_ref}": catalog,
            release_path: release,
            f"{source_root}/commits?sha={source_ref}&path=latest.json"
            "&until=2026-11-18T17:00:00Z&per_page=1": [{"sha": cutoff_ref}],
            f"{source_root}/contents/latest.json?ref={cutoff_ref}": old,
        }[path]

    assert set(health.check(NOW, request)["persistent_problems"]) == {"handoff", "catalog"}
    old.update(version=active["input_results_version"], checked_at=active["checked_at"])
    catalog["datasets"]["participation-native-bindings-2026"] = active["native"]
    assert not health.check(NOW, request)["persistent_problems"]
    release["assets"] = []
    assert set(health.check(NOW, request)["persistent_problems"]) == {"download"}


@pytest.mark.parametrize("archive_event", [None, "schedule", "workflow_dispatch"])
def test_weekly_health_only_accepts_named_success_and_checks_handoff(archive_event):
    now = datetime(2027, 2, 6, 19, tzinfo=timezone.utc)
    source_ref, runtime_ref = "1" * 40, "2" * 40
    active = {"version": "c" * 64, "input_results_version": "b" * 64,
              "checked_at": "2027-01-30T00:00:00Z", "counts": {}, "native": {}}
    source = {"version": "a" * 64, "checked_at": "2027-02-01T10:20:00Z"}
    catalog = {"datasets": {"participation-counts-2026": {}, "participation-native-bindings-2026": {}}}
    release_path, release = downloadable_runtime(active)
    ordinary = {**run(1, 0), "created_at": "2027-02-01T12:23:00Z", "updated_at": "2027-02-01T12:24:00Z",
                "head_branch": "main", "event": "schedule", "display_title": "Collect full election results"}
    archive = {**ordinary, "id": 101, "event": archive_event or "schedule",
               "display_title": health.ARCHIVE_TITLE,
               "conclusion": "cancelled" if archive_event is None else "success",
               "created_at": "2027-02-01T10:19:00Z", "updated_at": "2027-02-01T10:25:00Z"}
    pages = []

    def request(path, raw=False):
        if "/actions/" in path:
            query = parse_qs(urlsplit(path).query)
            assert "event" not in query and query["created"] == ["2027-02-01T10:19:00Z..2027-02-06T19:00:00Z"]
            page = int(query["page"][0])
            pages.append(page)
            history = [{**ordinary, "id": i} for i in range(1, 101)] if page == 1 else [archive]
            return {"total_count": 101, "workflow_runs": history}
        return {
            f"repos/{health.SOURCE}/git/ref/tags/results-data": {"object": {"type": "commit", "sha": source_ref}},
            f"repos/{health.WEBSITE}/git/ref/tags/participation-data": {"object": {"type": "commit", "sha": runtime_ref}},
            f"repos/{health.SOURCE}/contents/latest.json?ref={source_ref}": source,
            f"repos/{health.WEBSITE}/contents/automatic/latest.json?ref={runtime_ref}": active,
            f"repos/{health.WEBSITE}/contents/catalog.json?ref={runtime_ref}": catalog,
            release_path: release,
        }[path]

    observed = health.check(now, request)
    assert pages == [1, 2]
    assert set(observed["scheduled_writers"]) == {"weekly_archive"}
    if archive_event is None:
        assert set(observed["persistent_problems"]) == {"weekly_archive", "handoff"}
        assert observed["scheduled_writers"]["weekly_archive"]["last_success_id"] is None
    else:
        assert set(observed["persistent_problems"]) == {"handoff"}
        assert observed["scheduled_writers"]["weekly_archive"]["last_success_id"] == 101
        active["input_results_version"] = source["version"]
        assert not health.check(now, request)["persistent_problems"]


def test_first_weekly_slot_is_not_due_during_grace_and_incomplete_history_is_not_a_miss():
    def unexpected(*args):
        pytest.fail("No archive run is due")

    assert health.weekly_archive_status(datetime(2027, 2, 1, 13, 18, tzinfo=timezone.utc), unexpected) is None
    with pytest.raises(ValueError, match="Incomplete weekly collection history"):
        health.weekly_archive_status(datetime(2027, 2, 1, 13, 19, tzinfo=timezone.utc),
                                    lambda _: {"total_count": 1, "workflow_runs": []})
