from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from unittest.mock import patch

import pytest
import yaml


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/election-night.yml"


def workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_collection_has_its_own_budget_after_successful_pinned_validation():
    jobs = workflow()["jobs"]
    refresh = jobs["refresh"]
    validation = jobs[refresh["needs"]]
    assert refresh["if"] == "needs.validate.outputs.active == 'true'"
    assert validation["outputs"]["active"] == "${{ steps.window.outputs.active }}"
    assert refresh["timeout-minutes"] == validation["timeout-minutes"] == "30"
    assert validation["permissions"] == {"contents": "read"}
    for job in (validation, refresh):
        checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
        assert checkout["with"]["ref"] == "${{ github.sha }}"
    checkout = next(step for step in validation["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert ".github" in checkout["with"]["sparse-checkout"].split()
    assert any("python -m pytest" in step.get("run", "") for step in validation["steps"])
    assert not any("scripts.results_intake" in step.get("run", "") for step in validation["steps"])
    assert not any("python -m pytest" in step.get("run", "") for step in refresh["steps"])
    assert not any("steps.window" in step.get("if", "") for step in refresh["steps"])
    capture = next(step for step in refresh["steps"] if step.get("id") == "capture")
    assert capture["continue-on-error"] == "true"
    publication = next(step for step in refresh["steps"] if step.get("id") == "publication")
    assert "steps.capture.outcome == 'failure'" in publication["if"]
    assert "steps.restore.outputs.status == 'restored'" in publication["if"]
    assert "steps.saved.outcome == 'success'" in publication["if"]
    checkpoint = next(step for step in refresh["steps"] if step.get("id") == "saved")
    assert refresh["steps"].index(capture) < refresh["steps"].index(checkpoint) < refresh["steps"].index(publication)
    assert "complete-results.zip" in checkpoint["with"]["path"]
    assert "publication-parent.json" in checkpoint["with"]["path"]
    assert refresh["steps"][-1]["run"] == "exit 1"


@pytest.mark.parametrize("receipt,matched", [
    (None, False), (b"other\n", False), (b"expected\nextra", False), (b"expected\n", True),
])
def test_repeat_validation_requires_an_exact_success_receipt(tmp_path, receipt, matched):
    steps = workflow()["jobs"]["validate"]["steps"]
    restore = next(step for step in steps if step.get("id") == "prior_validation")
    check = next(step for step in steps if step.get("id") == "validation_receipt")
    tests = next(step for step in steps if step.get("id") == "validation_tests")
    save = next(step for step in steps if step.get("uses", "").startswith("actions/cache/save@"))
    assert "restore-keys" not in restore["with"] and restore["with"] == save["with"]
    assert "steps.prior_validation.outputs.cache-hit == 'true'" in check["if"]
    assert "steps.validation_receipt.outputs.matched != 'true'" in tests["if"]
    assert "steps.validation_tests.outcome == 'success'" in save["if"]
    output = tmp_path / "github-output"
    if receipt is not None:
        (tmp_path / "election-validation-receipt").write_bytes(receipt)
    script = check["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    with patch.dict(os.environ, {"RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(output), "EXPECTED": "expected"}):
        exec(compile(script, str(WORKFLOW), "exec"), {})
    assert output.read_text() == f"matched={str(matched).lower()}\n"


def test_validation_cache_changes_with_code_or_environment(tmp_path):
    gate = next(step for step in workflow()["jobs"]["validate"]["steps"] if step.get("id") == "validation_env")
    script = gate["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    output = tmp_path / "github-output"

    def fingerprint(sha="a" * 40, image="1", installed="pytest==8.4\n"):
        output.write_text("")
        with patch.dict(os.environ, {"GITHUB_SHA": sha, "ImageOS": "ubuntu24", "ImageVersion": image,
                                     "GITHUB_OUTPUT": str(output)}):
            with patch("subprocess.check_output", return_value=installed):
                exec(compile(script, str(WORKFLOW), "exec"), {})
        return output.read_text()

    baseline = fingerprint()
    assert baseline.startswith("fingerprint=") and len(baseline.strip().split("=", 1)[1]) == 64
    assert fingerprint() == baseline
    assert fingerprint(sha="b" * 40) != baseline
    assert fingerprint(image="2") != baseline
    assert fingerprint(installed="pytest==8.5\n") != baseline
    assert fingerprint(image="") == ""


@pytest.mark.parametrize("event,title,conclusion,publication,recoverable", [
    ("schedule", "Old title", "cancelled", "skipped", True),
    ("schedule", "Check late participation archives", "cancelled", "skipped", False),
    ("workflow_dispatch", "Collect full election results", "timed_out", "cancelled", True),
    ("workflow_dispatch", "Collect full election results", "failure", "failure", False),
    ("workflow_dispatch", "Collect full election results", "success", "success", False),
    ("workflow_dispatch", "Old title", "cancelled", "skipped", False),
])
def test_full_checkpoint_is_reused_only_for_interrupted_publication(
        tmp_path, event, title, conclusion, publication, recoverable):
    step = next(step for step in workflow()["jobs"]["refresh"]["steps"] if step.get("id") == "checkpoint")
    assert "inputs.refresh_sources == ''" in step["if"]
    assert "inputs.reuse_collection_run == ''" in step["if"]
    assert "!inputs.congressional_only" in step["if"]
    script = step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    output = tmp_path / "github-output"
    output.touch()
    metadata = [
        {"workflow_runs": [
            {"id": 124, "event": "workflow_dispatch", "display_title": "Run scoped election results update",
             "conclusion": "cancelled"},
            {"id": 123, "event": event, "display_title": title, "conclusion": conclusion},
            {"id": 122, "event": "workflow_dispatch", "display_title": title, "conclusion": "cancelled"},
        ]},
        {"jobs": [{"steps": [
            {"name": "Checkpoint the completed collection before publication", "conclusion": "success"},
            {"name": "Publish valid results or preserve new access stops", "conclusion": publication},
        ]}]},
    ]
    with patch.dict(os.environ, {"GH_REPO": "fixture/fixture", "GITHUB_OUTPUT": str(output),
                                 "LATE_ARCHIVES": "false"}):
        with patch("subprocess.check_output", side_effect=[json.dumps(body).encode() for body in metadata]) as api:
            exec(compile(script, str(WORKFLOW), "exec"), {})
    assert api.call_count == (2 if (event == "schedule" and title != "Check late participation archives") or (
        title == "Collect full election results" and conclusion != "success") else 1)
    if api.call_count == 2:
        assert api.call_args.args[0][-1].endswith("/runs/123/jobs")
    assert output.read_text() == ("run=123\n" if recoverable else "")


@pytest.mark.parametrize("event,conclusion,publication,recoverable", [
    ("schedule", "cancelled", "skipped", True),
    ("workflow_dispatch", "timed_out", "cancelled", True),
    ("schedule", "failure", "failure", False),
    ("schedule", "success", "success", False),
])
def test_weekly_checkpoint_search_skips_hourly_pages(tmp_path, event, conclusion, publication, recoverable):
    step = next(step for step in workflow()["jobs"]["refresh"]["steps"] if step.get("id") == "checkpoint")
    script = step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    output = tmp_path / "github-output"
    output.touch()
    hourly = {"event": "schedule", "display_title": "Collect full election results", "conclusion": "success"}
    manual = {"event": "workflow_dispatch", "display_title": "Run scoped election results update",
              "id": 124, "conclusion": "cancelled"}
    weekly = {"event": event, "display_title": "Check late participation archives",
              "id": 123, "conclusion": conclusion}
    metadata = [
        {"workflow_runs": [{**hourly, "id": 1000 + index} for index in range(100)]},
        {"workflow_runs": [manual, weekly, {**weekly, "id": 122, "conclusion": "cancelled"}]},
        {"jobs": [{"steps": [
            {"name": "Checkpoint the completed collection before publication", "conclusion": "success"},
            {"name": "Publish valid results or preserve new access stops", "conclusion": publication},
        ]}]},
    ]
    with patch.dict(os.environ, {"GH_REPO": "fixture/fixture", "GITHUB_OUTPUT": str(output),
                                 "LATE_ARCHIVES": "true"}):
        with patch("subprocess.check_output", side_effect=[json.dumps(body).encode() for body in metadata]) as api:
            exec(compile(script, str(WORKFLOW), "exec"), {})
    assert api.call_count == (2 if conclusion == "success" else 3)
    assert api.call_args_list[1].args[0][-1].endswith("&page=2")
    if api.call_count == 3:
        assert api.call_args.args[0][-1].endswith("/runs/123/jobs")
    assert output.read_text() == ("run=123\n" if recoverable else "")


@pytest.mark.parametrize(
    "now,event,schedule,active,late_archives",
    [
        ("2026-11-02T23:59:59+00:00", "schedule", "23 * * * *", False, False),
        ("2026-11-03T00:00:00+00:00", "schedule", "23 * * * *", True, False),
        ("2027-01-31T23:59:59+00:00", "schedule", "23 * * * *", True, False),
        ("2027-02-01T00:00:00+00:00", "schedule", "23 * * * *", False, False),
        ("2027-01-25T10:19:00+00:00", "schedule", "19 10 * * 1", False, False),
        ("2027-02-01T10:19:00+00:00", "schedule", "19 10 * * 1", True, True),
        ("2027-02-01T00:00:00+00:00", "workflow_dispatch", "", True, False),
    ],
)
def test_actual_window_output_controls_downstream_collection(tmp_path, now, event, schedule, active, late_archives):
    gate = next(step for step in workflow()["jobs"]["validate"]["steps"] if step.get("id") == "window")
    script = textwrap.dedent(gate["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0])
    output = tmp_path / "github-output"

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(now).astimezone(tz or timezone.utc)

    with patch.dict(os.environ, {"EVENT_NAME": event, "SCHEDULE": schedule, "GITHUB_OUTPUT": str(output),
                                 "ARCHIVE_ONLY": "", "REUSE_COLLECTION_RUN": "", "REFRESH_SOURCES": "",
                                 "CONGRESSIONAL_ONLY": "", "GITHUB_REF": "refs/heads/main"}):
        with patch("datetime.datetime", FrozenDateTime):
            exec(compile(script, str(WORKFLOW), "exec"), {})
    assert output.read_text() == f"active={str(active).lower()}\nlate_archives={str(late_archives).lower()}\n"


@pytest.mark.parametrize("early,override", [
    (False, {}), (False, {"GITHUB_REF": "refs/heads/other"}), (False, {"REFRESH_SOURCES": "not-an-archive"}),
    (False, {"REUSE_COLLECTION_RUN": "123"}), (False, {"CONGRESSIONAL_ONLY": "true"}), (True, {}),
])
def test_archive_recovery_is_scoped_or_refused(tmp_path, early, override):
    gate = next(step for step in workflow()["jobs"]["validate"]["steps"] if step.get("id") == "window")
    script = textwrap.dedent(gate["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0])
    output = tmp_path / "github-output"
    env = {"EVENT_NAME": "workflow_dispatch", "SCHEDULE": "", "GITHUB_OUTPUT": str(output),
           "ARCHIVE_ONLY": "true", "REUSE_COLLECTION_RUN": "", "REFRESH_SOURCES": "",
           "CONGRESSIONAL_ONLY": "false", "GITHUB_REF": "refs/heads/main"}

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2027, 1, 31, 23, 59, tzinfo=tz) if early else datetime(
                2027, 2, 1, 10, 20, tzinfo=tz)

    with patch.dict(os.environ, {**env, **override}), patch("datetime.datetime", FrozenDateTime):
        if early or override:
            with pytest.raises(SystemExit, match="Archive recovery requires"):
                exec(compile(script, str(WORKFLOW), "exec"), {})
            assert not output.exists()
        else:
            exec(compile(script, str(WORKFLOW), "exec"), {})
            assert output.read_text() == "active=true\nlate_archives=true\n"


@pytest.mark.parametrize("late_archives", [False, True])
def test_staged_publication_does_not_replace_the_weekly_check(tmp_path, late_archives):
    steps = workflow()["jobs"]["refresh"]["steps"]
    resume = next(step for step in steps if step.get("id") == "resume")
    capture = next(step for step in steps if step.get("id") == "capture")
    assert "(needs.validate.outputs.late_archives == 'true' && steps.resume.outputs.status == 'published')" in capture["if"]
    assert "steps.restore.outputs.status == 'superseded'" in capture["if"]
    assert "(needs.validate.outputs.late_archives == 'true' && steps.capture.outcome != 'success' && steps.restore.outputs.status != 'restored')" in steps[-1]["if"]

    commands = tmp_path / "commands"
    env = {**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "output"),
           "LATE_ARCHIVES": str(late_archives).lower(), "REFRESH_SOURCES": "",
           "CONGRESSIONAL_ONLY": "false", "COMMANDS": str(commands)}
    stub = """python() {
      if [ "$1" = "-c" ]; then
        printf 'published\\n'
      elif [ "$3" = "resume-publication" ]; then
        printf '{"status":"published"}\\n'
      else
        printf '%s\\n' "$@" > "$COMMANDS"
      fi
    }
    """
    subprocess.run(["bash", "-e", "-c", stub + resume["run"]], env=env, check=True)
    work = tmp_path / "election-intake"
    assert json.loads((work / "resume.json").read_bytes()) == {"status": "published"}
    assert (work / "publication.json").exists() is (not late_archives)
    if late_archives:
        subprocess.run(["bash", "-e", "-c", stub + capture["run"]], env=env, check=True)
        assert commands.read_text().splitlines()[:4] == [
            "-m", "scripts.results_intake", "refresh-selected", "--late-archives",
        ]


def test_late_archive_cli_uses_all_reviewed_towns_without_full_collection(tmp_path, monkeypatch):
    from scripts import results_intake, results_turnout_history as history

    town = "NH-test-municipal-turnout"
    monkeypatch.setitem(history.VOTINGWORKS_TOWNS, town, replace(
        history.VOTINGWORKS_TOWNS[history.HOLLIS_FEED], feed=town))
    monkeypatch.setattr(sys, "argv", ["results_intake", "refresh-selected", "--late-archives",
                                     "--registry", "registry.json", "--work-dir", str(tmp_path)])
    prev = {"source_stops": {"urls": ["https://example.test/denied"]}}
    with patch.object(results_intake, "publisher_state", return_value=(None, prev)), \
            patch.object(results_intake, "refresh_selected", return_value={}) as selected, \
            patch.object(results_intake, "collect", side_effect=AssertionError("unexpected full collection")):
        results_intake.main()
    _, _, state, sources = selected.call_args.args
    assert state is prev
    assert selected.call_args.kwargs == {"late_archives": True}
    assert len(sources) == len(set(sources))
    assert set(sources) == {
        "KS-general-election-turnout-workbook", "NJ-general-election-turnout-pdf",
        "PA-2026-general-vote-history", "TX-general-election-turnout",
        "VA-general-election-turnout", "WA-general-election-turnout",
        "MN-native-local", "MN-statewide-reporting",
        "NC-2026-general-vote-history", "NC-general-election-turnout-history", "UF-national-turnout",
        "WY-primary-general-turnout-profile",
        "HI-official-house-candidates", "IA-official-statewide-results", "NE-official-house-candidates",
        "OR-official-house-candidates", "RI-official-house-candidates", "RI-official-senate-candidates",
        "UT-official-house-candidates", "WY-official-house-candidates",
        "IN-2022-general-turnout-and-registration", "IN-2024-general-turnout-and-registration",
        "IN-2026-general-turnout-and-registration",
        "KS-2022-general-election-turnout-workbook",
        "NJ-2020-general-election-turnout-pdf", "NJ-2022-general-election-turnout-pdf",
        "NJ-2023-general-election-turnout-pdf",
        "NJ-2024-general-election-turnout-pdf", "NJ-2025-general-election-turnout-pdf",
        *(f"CA-{year}-general-election-turnout-pdf" for year in range(1998, 2025, 2)),
        *(f"CA-{year}-general-election-turnout-pdf" for year in (1990, 1992, 1994)),
        *(f"WV-{year}-general-election-turnout-pdf" for year in range(2008, 2017, 2)),
        *(f"WY-{year}-general-election-ballots-pdf" for year in range(2004, 2025, 2)),
        "CA-2026-general-election-turnout-pdf",
        "ME-bath-municipal-turnout", "ME-buxton-town-turnout", "NH-bedford-municipal-turnout",
        "NH-hanover-municipal-turnout", "NH-hollis-municipal-turnout", town,
    }
