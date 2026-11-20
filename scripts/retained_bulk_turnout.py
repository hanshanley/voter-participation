"""Use reviewed historical facts only when the collector has no accepted edition."""
import gzip
import json

from scripts import oregon_turnout_history, washington_participation
from scripts.participation_intake.contract import pin

MEMBER = "reviewed-bulk-turnout-archive.json.gz"
INPUT = "data/results-intake/" + MEMBER
PIN = {"bytes": 832907, "sha256": "98fea4b12582bfc3d4c7e165ae1bab17d9cb9c12793868be61f134cb97da4c01"}
FEEDS = {washington_participation.FEED, "MN-2006-general-precinct-turnout-workbook", *oregon_turnout_history.URLS}


def historical_entries(entries, body):
    if body is None:
        return entries
    if pin(body) != PIN:
        raise ValueError("Reviewed bulk turnout archive checksum differs")
    archive = json.loads(gzip.decompress(body))
    if set(archive) != FEEDS:
        raise ValueError("Reviewed bulk turnout archive scope differs")
    return {**entries, **{
        feed: {**fallback, "status": "retained_after_failure",
               "archive_status": "reviewed_historical_archive",
               "latest_acquisition_status": entries.get(feed, {}).get("status", "not_checked")}
        for feed, fallback in archive.items() if not entries.get(feed, {}).get("data")
    }}


def disposition(entry):
    return {key: entry[key] for key in ("archive_status", "latest_acquisition_status") if key in entry}
