"""Use reviewed historical facts only when the collector has no accepted edition."""
import gzip
import json

from scripts import dakota_turnout_history, idaho_turnout_history, oregon_turnout_history, washington_participation
from scripts.participation_intake.contract import pin

MEMBER = "reviewed-bulk-turnout-archive.json.gz"
INPUT = "data/results-intake/" + MEMBER
PRIOR_PIN = {"bytes": 832907, "sha256": "98fea4b12582bfc3d4c7e165ae1bab17d9cb9c12793868be61f134cb97da4c01"}
DAKOTA_PIN = {"bytes": 844704, "sha256": "a8a279bced54488826db2a688c35739a97113898cf7cd99858e7225a6cd2ab65"}
IDAHO_PIN = {"bytes": 860417, "sha256": "f34f02ad847ba948e48f9eedf82660dabab544f64a9c9312af5fc2be9cbb007b"}
PIN = {"bytes": 862736, "sha256": "a0279e8d48f9cb05ce14ce989b90d1a1650ac9274ca38bfe502248ee83baa885"}
PRIOR_FEEDS = {washington_participation.FEED, "MN-2006-general-precinct-turnout-workbook", *oregon_turnout_history.URLS}
DAKOTA_FEEDS = PRIOR_FEEDS | dakota_turnout_history.URLS.keys()
IDAHO_FEEDS = DAKOTA_FEEDS | {idaho_turnout_history.FEED}
FEEDS = IDAHO_FEEDS | idaho_turnout_history.COUNTY_FEEDS.keys()


def historical_entries(entries, body):
    if body is None:
        return entries
    actual = pin(body)
    match = next((feeds for version, feeds in ((PIN, FEEDS), (IDAHO_PIN, IDAHO_FEEDS),
                 (DAKOTA_PIN, DAKOTA_FEEDS), (PRIOR_PIN, PRIOR_FEEDS)) if actual == version), None)
    if match is None:
        raise ValueError("Reviewed bulk turnout archive checksum differs")
    archive = json.loads(gzip.decompress(body))
    if set(archive) != match:
        raise ValueError("Reviewed bulk turnout archive scope differs")
    return {**entries, **{
        feed: {**fallback, "status": "retained_after_failure",
               "archive_status": "reviewed_historical_archive",
               "latest_acquisition_status": entries.get(feed, {}).get("status", "not_checked")}
        for feed, fallback in archive.items() if not entries.get(feed, {}).get("data")
    }}


def disposition(entry):
    return {key: entry[key] for key in ("archive_status", "latest_acquisition_status") if key in entry}
