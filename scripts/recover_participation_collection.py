"""Recover a missed collection via the existing GitHub Actions writer lane."""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

from scripts.automatic_health import ARCHIVE_START, ARCHIVE_TITLE, HOURLY_START, SOURCE, WEBSITE, clock, data_commit


WORKFLOW = f"repos/{SOURCE}/actions/workflows/election-night.yml"
GROUPS = f"repos/{SOURCE}/actions/concurrency_groups?per_page=100"
WRITER = "election-night-participation"
FULL_TITLE = "Collect full election results"
HOURLY = "47 * * * *"
WEEKLY = "47 13 * * 1,3"
ACTIVE = {"queued", "in_progress", "requested", "waiting", "pending"}


def api(path, body=None):
    command = ["gh", "api", path]
    if body is not None:
        command.extend(["--method", "POST", "--input", "-"])
    result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                            text=True, capture_output=True, check=True, timeout=30)
    return json.loads(result.stdout) if result.stdout else None


def public_pointer(repository, tag, file):
    def public_api(path):
        with urlopen("https://api.github.com/" + path, timeout=15) as response:
            return json.load(response)

    commit = data_commit(repository, tag, public_api)
    with urlopen(f"https://raw.githubusercontent.com/{repository}/{commit}/{file}", timeout=15) as response:
        return json.load(response)


def published_handoff(now, pointer=public_pointer):
    source = pointer(SOURCE, "results-data", "latest.json")
    runtime = pointer(WEBSITE, "participation-data", "automatic/latest.json")
    if (source.get("contract") != "participation.automatic_results_latest.v1"
            or runtime.get("contract") != "participation.automatic_runtime.v1"
            or not all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value)
                       for value in (source.get("version"), runtime.get("version"),
                                     runtime.get("input_results_version")))):
        raise ValueError("Invalid collection or publication pointer")
    checked = clock(source["checked_at"]), clock(runtime["checked_at"])
    if not all(HOURLY_START <= value <= now for value in checked):
        return "checkpoint_clock_unverified"
    if source["version"] != runtime["input_results_version"]:
        return "awaiting_publication"
    if checked[0] != checked[1]:
        return "checkpoint_clock_unverified"
    return None


def recovery(now, schedule, request=api, *, apply=False, handoff=published_handoff):
    now = now.astimezone(timezone.utc)
    late = schedule == WEEKLY
    if (schedule not in {HOURLY, WEEKLY} or now < HOURLY_START
            or late != (now >= ARCHIVE_START)):
        return {"decision": "outside_collection_window"}

    if late:
        since = (now - timedelta(days=now.weekday())).replace(hour=10, minute=19, second=0, microsecond=0)
        if now < since + timedelta(hours=3):
            return {"decision": "archive_grace_period"}
    else:
        since = now - timedelta(hours=6)

    query = urlencode({"branch": "main", "created": f">={since:%Y-%m-%dT%H:%M:%SZ}", "per_page": 100})
    page = request(f"{WORKFLOW}/runs?{query}")
    runs = page["workflow_runs"]
    if len(runs) != page["total_count"]:
        raise ValueError("Incomplete collector history; no recovery dispatch")
    lane = []
    for run in runs:
        status, created = run["status"], clock(run["created_at"])
        if (run["head_branch"] != "main" or type(run["id"]) is not int or run["id"] <= 0
                or not since.replace(microsecond=0) <= created <= now
                or status not in ACTIVE | {"completed"}):
            raise ValueError("Invalid collector run in recovery history")
        if status in ACTIVE:
            return {"decision": "collector_active", "run_id": run["id"]}
        if (run["event"] in {"schedule", "workflow_dispatch"}
                and run["display_title"] == (ARCHIVE_TITLE if late else FULL_TITLE)):
            lane.append(run)

    latest = max(lane, key=lambda run: (clock(run["created_at"]), run["id"]), default=None)
    if late and any(run["conclusion"] == "success" for run in lane):
        return {"decision": "weekly_archive_already_checked"}
    if latest:
        updated = clock(latest["updated_at"])
        if not clock(latest["created_at"]) <= updated <= now:
            raise ValueError("Invalid collector completion clock")
        if latest["conclusion"] != "success":
            cooldown = timedelta(hours=6) if late else timedelta(minutes=30)
            if now - updated < cooldown:
                return {"decision": "collector_retry_cooldown", "run_id": latest["id"]}
            reason = "collector_failed"
        elif now - clock(latest["created_at"]) < timedelta(minutes=90):
            return {"decision": "recent_full_collection", "run_id": latest["id"]}
        else:
            reason = "collector_schedule_missed"
    else:
        reason = "weekly_archive_missed" if late else "collector_schedule_missed"

    # The paged history can miss an older or just-queued writer.
    groups = request(GROUPS)
    names = [entry["group_name"] for entry in groups["concurrency_groups"]]
    if len(names) != groups["total_count"] or any(not isinstance(name, str) for name in names):
        raise ValueError("Incomplete collector concurrency inventory")
    if WRITER in {name.casefold() for name in names}:
        return {"decision": "collector_active"}
    if pending := handoff(now):
        return {"decision": pending}
    report = {"decision": "would_dispatch", "reason": reason, "archive_only": late}
    if apply:
        request(f"{WORKFLOW}/dispatches", {"ref": "main", "inputs": {"archive_only": late}})
        report["decision"] = "dispatched"
    return report


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    event = os.environ.get("GITHUB_EVENT_NAME")
    if (os.environ.get("GITHUB_REPOSITORY") != SOURCE
            or os.environ.get("GITHUB_REF") != "refs/heads/main"):
        raise SystemExit("Recovery is restricted to the canonical research repository and branch")
    schedule = os.environ.get("RECOVERY_SCHEDULE") if event == "schedule" else (
        WEEKLY if now >= ARCHIVE_START else HOURLY)
    print(json.dumps(recovery(now, schedule, apply=event == "schedule"), sort_keys=True))
