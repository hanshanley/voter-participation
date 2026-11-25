"""Check scheduled election intake and publication without running either writer."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SOURCE = "hanshanley/voter-participation"
WEBSITE = "hanshanley/margin_of_error"
MONITORS = {
    "collection": (SOURCE, "election-night.yml"),
    "publication": (WEBSITE, "automatic-runtime.yml"),
}
NO_SUCCESS_LIMIT = timedelta(hours=3)
HANDOFF_LIMIT = timedelta(hours=2)
HOURLY_START = datetime(2026, 11, 3, tzinfo=timezone.utc)
ARCHIVE_START = datetime(2027, 2, 1, tzinfo=timezone.utc)
ARCHIVE_TITLE = "Check late participation archives"
TITLE = "Automatic voter-participation updates need attention"
MARKER = "<!-- voter-participation-automatic-health:v1 -->"
RATE_LIMIT_WAIT_BUDGET = 120
RATE_LIMIT_RETRIES = 2


def clock(value):
    observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if observed.utcoffset() is None:
        raise ValueError("Missing UTC offset in update evidence")
    return observed


def api(path, method="GET", body=None, raw=False):
    public = path.startswith((f"repos/{SOURCE}/", f"repos/{WEBSITE}/releases/tags/automatic-participation-"))
    if public:
        if method != "GET" or body is not None:
            raise ValueError("Public evidence requests are read-only")
        # The website's Actions token is confined to the website repository.
        headers = {"Accept": "application/vnd.github.raw+json"} if raw else {}
        with urlopen(Request("https://api.github.com/" + path, headers=headers), timeout=30) as response:
            return json.load(response)
    args = ["gh", "api", "--method", method, path]
    if body is not None:
        args += ["--input", "-"]
    if raw:
        args += ["-H", "Accept: application/vnd.github.raw+json"]
    return json.loads(subprocess.run(
        args, input=json.dumps(body) if body is not None else None,
        text=True, stdout=subprocess.PIPE, check=True, timeout=60).stdout)


def is_rate_limited(error):
    headers = {key.lower(): value for key, value in (error.headers or {}).items()}
    return error.code == 429 or (error.code == 403 and (
        headers.get("x-ratelimit-remaining") == "0"
        or "retry-after" in headers or "rate limit" in str(error.reason).lower()))


def retry_delay(error, attempt):
    if not is_rate_limited(error):
        return None
    headers = {key.lower(): value for key, value in (error.headers or {}).items()}
    delays = []
    if "retry-after" in headers:
        if not str(headers["retry-after"]).isdigit():
            return None
        delays.append(int(headers["retry-after"]))
    if headers.get("x-ratelimit-remaining") == "0":
        reset = str(headers.get("x-ratelimit-reset", ""))
        if not reset.isdigit():
            return None
        delays.append(int(reset) - time.time() + 1)
    return max(1, *delays) if delays else 60 * 2 ** attempt


def recovering_requests(request):
    waited = 0

    def recover(path, method="GET", body=None, raw=False):
        nonlocal waited
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                return request(path, method, body, raw=raw)
            except HTTPError as error:
                delay = retry_delay(error, attempt)
                if (method != "GET" or body is not None or delay is None
                        or attempt == RATE_LIMIT_RETRIES
                        or waited + delay > RATE_LIMIT_WAIT_BUDGET):
                    error.monitoring_request = path
                    error.monitoring_waited_seconds = waited
                    raise
                print(f"GitHub evidence throttled; retrying read in {delay:.0f}s: {path}", file=sys.stderr)
                error.close()
                time.sleep(delay)
                waited += delay
    return recover


def data_commit(repository, tag, request):
    ref = request(f"repos/{repository}/git/ref/tags/{tag}")["object"]
    if ref["type"] != "commit" or not re.fullmatch(r"[a-f0-9]{40}", ref["sha"]):
        raise ValueError("Automatic data ref did not resolve to a commit")
    return ref["sha"]


def contents(repository, commit, name, request):
    return request(f"repos/{repository}/contents/{name}?ref={commit}", raw=True)


def complete_download_status(active, request):
    tag = "automatic-participation-" + active["version"]
    url = f"https://github.com/{WEBSITE}/releases/download/{tag}/complete-analysis.zip"
    pin = active.get("complete_download")
    if (not isinstance(pin, dict) or pin.get("url") != url
            or type(pin.get("bytes")) is not int or pin["bytes"] <= 0
            or not isinstance(pin.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", pin["sha256"])
            or pin.get("verified_anonymously") is not True):
        return "invalid_manifest_download"
    # Query without credentials so a draft/private release can't pass this check.
    path = f"repos/{WEBSITE}/releases/tags/{tag}"
    try:
        release = request(path)
    except HTTPError as error:
        if error.code == 404:
            return "release_not_public"
        raise
    if release.get("draft") is not False or release.get("tag_name") != tag:
        return "release_not_public"
    assets = [asset for asset in release.get("assets", []) if asset.get("name") == "complete-analysis.zip"]
    if len(assets) != 1:
        return "missing_or_duplicate_complete_zip"
    asset = assets[0]
    if (asset.get("state") != "uploaded" or asset.get("browser_download_url") != url
            or asset.get("size") != pin["bytes"] or asset.get("digest") != "sha256:" + pin["sha256"]):
        return "complete_zip_differs_from_manifest"
    return "verified"


def assess(now, runs, source, active, *, source_at_cutoff=None, catalog=None):
    problems, recent_failures, stages = {}, {}, {}
    for stage, history in runs.items():
        ordered = sorted(history, key=lambda run: (clock(run["created_at"]), run["id"]), reverse=True)
        finished = [run for run in ordered if run["status"] == "completed"]
        success = next((run for run in finished if run["conclusion"] == "success"), None)
        consecutive = []
        for run in finished:
            if run["conclusion"] == "success":
                break
            consecutive.append(run)
        if consecutive:
            recent_failures[stage] = [run["id"] for run in consecutive]
        stages[stage] = {
            "last_run_id": ordered[0]["id"] if ordered else None,
            "last_run_at": ordered[0]["created_at"] if ordered else None,
            "last_success_id": success["id"] if success else None,
            "last_success_at": success["updated_at"] if success else None,
        }
        if len(consecutive) >= 2:
            problems[stage] = f"{stage}: repeated scheduled failures (runs {consecutive[1]['id']}, {consecutive[0]['id']})."
        elif not success or now - clock(success["updated_at"]) >= NO_SUCCESS_LIMIT:
            problems[stage] = f"{stage}: no successful scheduled run in the last three hours."

    accepted_version = source["version"]
    active_input = active["input_results_version"]
    runtime_version = active["version"]
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
           for value in (accepted_version, active_input, runtime_version)):
        raise ValueError("Invalid source or active runtime version")
    caught_up = accepted_version == active_input
    sources_checked_at = clock(source["checked_at"])
    active_checked_at = clock(active["checked_at"])
    if not (HOURLY_START <= sources_checked_at <= now and HOURLY_START <= active_checked_at <= now):
        problems["clock"] = "publication: a checkpoint is future-dated or predates the general-election window."
    cutoff_overdue = (source_at_cutoff is not None
                      and source_at_cutoff["version"] != active_input
                      and clock(source_at_cutoff["checked_at"]) > active_checked_at)
    if not caught_up and (now - sources_checked_at >= HANDOFF_LIMIT or cutoff_overdue):
        problems["handoff"] = (
            f"handoff: accepted source `{accepted_version}` is not the active input `{active_input}` "
            "after the two-hour grace period.")
    if catalog is not None and any(
        not isinstance(active.get(field), dict)
        or catalog["datasets"].get(identity) != active[field]
        for field, identity in (("counts", "participation-counts-2026"),
                                ("native", "participation-native-bindings-2026"))
    ):
        problems["catalog"] = "publication: the active runtime and data catalog disagree."
    return {
        "checked_at": now.isoformat(),
        "scheduled_writers": stages,
        "source": {"version": accepted_version, "collection_checked_at": source["checked_at"]},
        "active": {"version": runtime_version, "source_version": active_input,
                   "source_collection_checked_at": active["checked_at"]},
        "caught_up": caught_up,
        "recent_failures": recent_failures,
        "persistent_problems": problems,
    }


def update_issue(report, request):
    endpoint = f"repos/{WEBSITE}/issues"
    problems = report["persistent_problems"]
    # Look up only our marked issue; never edit a similarly titled human issue.
    issues = request(endpoint + "?state=open&creator=github-actions%5Bbot%5D&per_page=100")
    matching = [issue for issue in issues if issue["title"] == TITLE
                and (issue.get("body") or "").startswith(MARKER)
                and issue["user"]["login"] == "github-actions[bot]"]
    if len(matching) > 1:
        raise ValueError("Multiple open automatic-health issues; refusing ambiguous update")
    existing = matching[0] if matching else None
    if not problems:
        if existing and report["caught_up"] and not report["recent_failures"]:
            request(f"{endpoint}/{existing['number']}", "PATCH",
                    {"state": "closed", "state_reason": "completed"})
            return "closed"
        return "unchanged"
    body = (
        MARKER + "\n\n" + "\n".join(f"- {reason}" for reason in problems.values())
        + "\n\nLast-good data remain active. This alert tracks scheduled collection and data publication, "
        "not source-specific evidence holds or certification."
        + f"\n\n[Collector runs](https://github.com/{SOURCE}/actions/workflows/election-night.yml)"
        + f" · [Publisher runs](https://github.com/{WEBSITE}/actions/workflows/automatic-runtime.yml)\n"
    )
    if existing is None:
        request(endpoint, "POST", {"title": TITLE, "body": body})
        return "opened"
    if existing["body"] != body:
        request(f"{endpoint}/{existing['number']}", "PATCH", {"body": body})
        return "updated"
    return "unchanged"


def weekly_archive_status(now, request):
    due = (now - NO_SUCCESS_LIMIT).astimezone(timezone.utc)
    slot = (due - timedelta(days=due.weekday())).replace(hour=10, minute=19, second=0, microsecond=0)
    if slot > due:
        slot -= timedelta(days=7)
    if slot < ARCHIVE_START:
        return None

    repo, workflow = MONITORS["collection"]
    endpoint = f"repos/{repo}/actions/workflows/{workflow}/runs"
    seen = set()
    archive_runs = []
    for page in range(1, 5):
        created = f"{slot:%Y-%m-%dT%H:%M:%SZ}..{now.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"
        query = urlencode({"branch": "main", "created": created, "per_page": 100, "page": page})
        response = request(f"{endpoint}?{query}")
        history = response["workflow_runs"]
        for run in history:
            if (type(run["id"]) is not int or run["id"] in seen or run["head_branch"] != "main"
                    or not slot <= clock(run["created_at"]) <= now):
                raise ValueError("Inconsistent weekly collection history")
            seen.add(run["id"])
            if run.get("display_title") == ARCHIVE_TITLE and run["event"] in {"schedule", "workflow_dispatch"}:
                archive_runs.append(run)
        if len(seen) == response["total_count"]:
            break
        if len(history) < 100:
            raise ValueError("Incomplete weekly collection history")
    else:
        raise ValueError("Weekly collection history exceeded the inspection bound")
    ordered = sorted(archive_runs, key=lambda run: (clock(run["created_at"]), run["id"]), reverse=True)
    latest = next(iter(ordered), None)
    success = next((run for run in ordered if run["status"] == "completed" and run["conclusion"] == "success"), None)
    return {"due_at": slot.isoformat(), "last_run_id": latest["id"] if latest else None,
            "last_run_at": latest["created_at"] if latest else None,
            "last_success_id": success["id"] if success else None,
            "last_success_at": success["updated_at"] if success else None}


def check(now, request=api, *, write_issue=False, clock_now=None):
    if now < HOURLY_START:
        return {"status": "outside_collection_window"}
    hourly = now < ARCHIVE_START
    runs = {}
    if hourly:
        runs = {stage: request(
            f"repos/{repo}/actions/workflows/{name}/runs?branch=main&event=schedule&per_page=10"
        )["workflow_runs"] for stage, (repo, name) in MONITORS.items()}
    source_commit = data_commit(SOURCE, "results-data", request)
    runtime_commit = data_commit(WEBSITE, "participation-data", request)
    source = contents(SOURCE, source_commit, "latest.json", request)
    active = contents(WEBSITE, runtime_commit, "automatic/latest.json", request)
    catalog = contents(WEBSITE, runtime_commit, "catalog.json", request)
    if clock_now is not None:
        now = clock_now()
    source_at_cutoff = None
    cutoff = now - HANDOFF_LIMIT
    if (source["version"] != active["input_results_version"]
            and clock(active["checked_at"]) < cutoff < clock(source["checked_at"])):
        # A newer arrival must not reset the clock on an already lagging handoff.
        until = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        history = request(f"repos/{SOURCE}/commits?sha={source_commit}&path=latest.json"
                          f"&until={until}&per_page=1")
        if history:
            previous = history[0]["sha"]
            if not re.fullmatch(r"[a-f0-9]{40}", previous):
                raise ValueError("Invalid source history commit")
            source_at_cutoff = contents(SOURCE, previous, "latest.json", request)
    report = assess(now, runs, source, active, source_at_cutoff=source_at_cutoff,
                    catalog=catalog)
    status = complete_download_status(active, request)
    report["complete_download"] = status
    if status != "verified":
        report["persistent_problems"]["download"] = "publication: the public complete ZIP failed verification (" + status + ")."
    if not hourly and (weekly := weekly_archive_status(now, request)) is not None:
        report["scheduled_writers"]["weekly_archive"] = weekly
        if weekly["last_success_id"] is None:
            report["persistent_problems"]["weekly_archive"] = (
                f"weekly archive: no successful collection for the {weekly['due_at']} slot after the three-hour grace period.")
    report["issue_action"] = update_issue(report, request) if write_issue else "read_only"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-issue", action="store_true")
    args = parser.parse_args()
    rate_limited = False
    try:
        report = check(datetime.now(timezone.utc), recovering_requests(api), write_issue=args.update_issue,
                       clock_now=lambda: datetime.now(timezone.utc))
    except HTTPError as exc:
        if not is_rate_limited(exc):
            raise
        rate_limited = True
        report = {"status": "monitoring_unavailable", "reason": "github_api_rate_limited",
                  "issue_action": "unchanged", "request": getattr(exc, "monitoring_request", None),
                  "waited_seconds": getattr(exc, "monitoring_waited_seconds", 0),
                  "rate_limit_reset": {key.lower(): value for key, value in (exc.headers or {}).items()}
                      .get("x-ratelimit-reset")}
    body = json.dumps(report, indent=2)
    print(body)
    if filename := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(filename).open("a") as out:
            out.write("### Participation update health\n\n```json\n" + body + "\n```\n")
    if rate_limited:
        raise SystemExit(75)


if __name__ == "__main__":
    main()
