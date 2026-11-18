from datetime import datetime, timedelta, timezone

from scripts import automatic_health as health


NOW = datetime(2026, 11, 18, 19, tzinfo=timezone.utc)


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

    assert health.check(datetime(2027, 2, 1, tzinfo=timezone.utc), unexpected,
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
            f"{source_root}/commits?sha={source_ref}&path=latest.json"
            "&until=2026-11-18T17:00:00Z&per_page=1": [{"sha": cutoff_ref}],
            f"{source_root}/contents/latest.json?ref={cutoff_ref}": old,
        }[path]

    assert set(health.check(NOW, request)["persistent_problems"]) == {"handoff", "catalog"}
    old.update(version=active["input_results_version"], checked_at=active["checked_at"])
    catalog["datasets"]["participation-native-bindings-2026"] = active["native"]
    assert not health.check(NOW, request)["persistent_problems"]
