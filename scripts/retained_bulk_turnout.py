"""Use reviewed historical facts only when the collector has no accepted edition."""
import gzip
import json

from scripts import alaska_precinct_history, dakota_turnout_history, idaho_absentee_age, idaho_turnout_history, oregon_turnout_history, washington_participation
from scripts.participation_intake.contract import pin

MEMBER = "reviewed-bulk-turnout-archive.json.gz"
INPUT = "data/results-intake/" + MEMBER
PRIOR_PIN = {"bytes": 832907, "sha256": "98fea4b12582bfc3d4c7e165ae1bab17d9cb9c12793868be61f134cb97da4c01"}
DAKOTA_PIN = {"bytes": 844704, "sha256": "a8a279bced54488826db2a688c35739a97113898cf7cd99858e7225a6cd2ab65"}
IDAHO_PIN = {"bytes": 860417, "sha256": "f34f02ad847ba948e48f9eedf82660dabab544f64a9c9312af5fc2be9cbb007b"}
IDAHO_COUNTY_PIN = {"bytes": 862736, "sha256": "a0279e8d48f9cb05ce14ce989b90d1a1650ac9274ca38bfe502248ee83baa885"}
IDAHO_AGE_PIN = {"bytes": 863471, "sha256": "655849ad9753e82d122db2cb90c03edb69d30f130d24d592fb05f26c62b891d8"}
PIN = {"bytes": 875629, "sha256": "53ef4d5f8cb995c56294fbfb61889688f56d2efbb381a4648bfaf3f9bcaf4178"}
PRIOR_FEEDS = {washington_participation.FEED, "MN-2006-general-precinct-turnout-workbook", *oregon_turnout_history.URLS}
DAKOTA_FEEDS = PRIOR_FEEDS | dakota_turnout_history.URLS.keys()
IDAHO_FEEDS = DAKOTA_FEEDS | {idaho_turnout_history.FEED}
IDAHO_COUNTY_FEEDS = IDAHO_FEEDS | idaho_turnout_history.COUNTY_FEEDS.keys()
IDAHO_AGE_FEEDS = IDAHO_COUNTY_FEEDS | {idaho_absentee_age.FEED}
FEEDS = IDAHO_AGE_FEEDS | {alaska_precinct_history.MIDTERM_FEED}


def historical_entries(entries, body):
    if body is None:
        return entries
    actual = pin(body)
    match = next((feeds for version, feeds in ((PIN, FEEDS), (IDAHO_AGE_PIN, IDAHO_AGE_FEEDS),
                 (IDAHO_COUNTY_PIN, IDAHO_COUNTY_FEEDS), (IDAHO_PIN, IDAHO_FEEDS),
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
