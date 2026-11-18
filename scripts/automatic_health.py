"""Check scheduled election intake and publication without running either writer."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen


SOURCE = "hanshanley/voter-participation"
WEBSITE = "hanshanley/margin_of_error"
MONITORS = {
    "collection": (SOURCE, "election-night.yml"),
    "publication": (WEBSITE, "automatic-runtime.yml"),
}
NO_SUCCESS_LIMIT = timedelta(hours=3)
HANDOFF_LIMIT = timedelta(hours=2)
TITLE = "Automatic voter-participation updates need attention"
MARKER = "<!-- voter-participation-automatic-health:v1 -->"


def clock(value):
    observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if observed.utcoffset() is None:
        raise ValueError("Missing UTC offset in update evidence")
    return observed


def api(path, method="GET", body=None, raw=False):
    if path.startswith(f"repos/{SOURCE}/"):
        if method != "GET" or body is not None:
            raise ValueError("The source repository is read-only for the monitor")
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


def data_commit(repository, tag, request):
    ref = request(f"repos/{repository}/git/ref/tags/{tag}")["object"]
    if ref["type"] != "commit" or not re.fullmatch(r"[a-f0-9]{40}", ref["sha"]):
        raise ValueError("Automatic data ref did not resolve to a commit")
    return ref["sha"]


def contents(repository, commit, name, request):
    return request(f"repos/{repository}/contents/{name}?ref={commit}", raw=True)


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


def check(now, request=api, *, write_issue=False):
    if not (datetime(2026, 11, 3, tzinfo=timezone.utc) <= now <
            datetime(2027, 2, 1, tzinfo=timezone.utc)):
        return {"status": "outside_collection_window"}
    runs = {stage: request(
        f"repos/{repo}/actions/workflows/{name}/runs?branch=main&event=schedule&per_page=10"
    )["workflow_runs"] for stage, (repo, name) in MONITORS.items()}
    source_commit = data_commit(SOURCE, "results-data", request)
    runtime_commit = data_commit(WEBSITE, "participation-data", request)
    source = contents(SOURCE, source_commit, "latest.json", request)
    active = contents(WEBSITE, runtime_commit, "automatic/latest.json", request)
    catalog = contents(WEBSITE, runtime_commit, "catalog.json", request)
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
    report["issue_action"] = update_issue(report, request) if write_issue else "read_only"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-issue", action="store_true")
    args = parser.parse_args()
    report = check(datetime.now(timezone.utc), write_issue=args.update_issue)
    body = json.dumps(report, indent=2)
    print(body)
    if filename := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(filename).open("a") as out:
            out.write("### Participation update health\n\n```json\n" + body + "\n```\n")


if __name__ == "__main__":
    main()
