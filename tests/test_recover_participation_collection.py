from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, call

import pytest

from scripts import recover_participation_collection as recovery


HOURLY = datetime(2026, 11, 19, 13, 47, tzinfo=timezone.utc)
WEEKLY = datetime(2027, 2, 1, 13, 47, tzinfo=timezone.utc)


def run(now, age, *, title=recovery.FULL_TITLE, status="completed", conclusion="success",
        updated=None):
    created = now - timedelta(minutes=age)
    return {"id": 42, "head_branch": "main", "status": status, "event": "schedule",
            "display_title": title, "conclusion": conclusion, "created_at": created.isoformat(),
            "updated_at": (now - timedelta(minutes=updated)).isoformat() if updated is not None
            else created.isoformat()}


def request(runs, groups=()):
    return Mock(side_effect=[
        {"total_count": len(runs), "workflow_runs": runs},
        {"total_count": len(groups), "concurrency_groups": [{"group_name": name} for name in groups]},
        None,
    ])


@pytest.mark.parametrize(("evidence", "reason"), [
    (run(HOURLY, 20), "recent_full_collection"),
    (run(HOURLY, 20, status="queued"), "collector_active"),
    (run(HOURLY, 60, conclusion="failure", updated=29), "collector_retry_cooldown"),
])
def test_does_not_duplicate_recent_active_or_cooling_collection(evidence, reason):
    transport = request([evidence])
    assert recovery.recovery(HOURLY, recovery.HOURLY, transport, apply=True)["decision"] == reason
    transport.assert_called_once()


@pytest.mark.parametrize(("now", "schedule", "runs", "archive", "reason"), [
    (HOURLY, recovery.HOURLY, [run(HOURLY, 10, title="Run scoped election results update")],
     False, "collector_schedule_missed"),
    (HOURLY, recovery.HOURLY, [run(HOURLY, 82, conclusion="failure", updated=31)],
     False, "collector_failed"),
    (WEEKLY, recovery.WEEKLY, [run(WEEKLY, 20)], True, "weekly_archive_missed"),
])
def test_single_dispatch_only_when_appropriate(now, schedule, runs, archive, reason):
    transport = request(runs)
    assert recovery.recovery(now, schedule, transport, apply=True, handoff=lambda _: None) == {
        "decision": "dispatched", "archive_only": archive, "reason": reason}
    assert transport.call_args_list[-2:] == [
        call(recovery.GROUPS), call(recovery.WORKFLOW + "/dispatches",
                                  {"ref": "main", "inputs": {"archive_only": archive}})]
    assert transport.call_count == 3


def test_weekly_success_skips_backup_and_scoped_success_cannot_replace_it():
    transport = request([run(WEEKLY, 30, title=recovery.ARCHIVE_TITLE)])
    assert recovery.recovery(WEEKLY, recovery.WEEKLY, transport, apply=True)["decision"] == (
        "weekly_archive_already_checked")
    transport.assert_called_once()


def test_incomplete_history_and_concurrency_guard_are_fail_closed():
    transport = Mock(return_value={"total_count": 1, "workflow_runs": []})
    with pytest.raises(ValueError, match="Incomplete collector history"):
        recovery.recovery(HOURLY, recovery.HOURLY, transport, apply=True)
    transport.assert_called_once()
    transport = request([], [recovery.WRITER.upper()])
    assert recovery.recovery(HOURLY, recovery.HOURLY, transport, apply=True)["decision"] == "collector_active"
    assert transport.call_count == 2


def test_non_schedule_preview_has_no_write_and_outside_window_uses_no_api():
    transport = request([])
    assert recovery.recovery(HOURLY, recovery.HOURLY, transport, handoff=lambda _: None)["decision"] == "would_dispatch"
    assert transport.call_count == 2
    transport.reset_mock()
    assert recovery.recovery(WEEKLY, recovery.HOURLY, transport, apply=True)["decision"] == "outside_collection_window"
    transport.assert_not_called()


@pytest.mark.parametrize(("handoff", "clock_offset", "expected"), [
    (True, 0, "dispatched"), (False, 0, "awaiting_publication"),
    (True, 60, "checkpoint_clock_unverified"), (True, -60, "checkpoint_clock_unverified"),
])
def test_recovery_requires_an_exact_publication_handoff(handoff, clock_offset, expected):
    checked = HOURLY - timedelta(minutes=45)
    source = {"contract": "participation.automatic_results_latest.v1",
              "version": "a" * 64, "checked_at": checked.isoformat()}
    runtime = {"contract": "participation.automatic_runtime.v1", "version": "c" * 64,
               "input_results_version": ("a" if handoff else "b") * 64,
               "checked_at": (checked + timedelta(minutes=clock_offset)).isoformat()}
    read = Mock(side_effect=[source, runtime])
    transport = request([])
    result = recovery.recovery(HOURLY, recovery.HOURLY, transport, apply=True,
                               handoff=lambda now: recovery.published_handoff(now, read))
    assert result["decision"] == expected
    assert transport.call_count == (3 if expected == "dispatched" else 2)
