from datetime import datetime, timezone
import json

import pytest

from scripts import idaho_absentee_age as age
from scripts.participation_intake.contract import pin


def sources(*, version=76, day=5, returned=10, early=20):
    base = age.CHART + f"lYjhf/{version}/"
    embed = {"publicId": "lYjhf", "publishedAt": "2026-11-04T13:37:01.000Z",
             "publicUrl": base, "publicVersion": version,
             "lastModifiedAt": f"2026-11-{day:02d}T17:40:42.000Z",
             "assets": {"dataset.csv": {"load": True, "url": "dataset.csv"}}, "nextPublicUrl": base}
    return {
        age.INDEX: (f'Absentee &amp; Early Voting Stats - 2026 General Election\nvar dataPath = "{age.CONTROL}";'
                    '<h3>Absentee &amp; Early Voting By Age</h3><div id="datawrapper-vis-lYjhf">'
                    f'<script src="{age.CHART}lYjhf/embed.js">').encode(),
        age.CONTROL: json.dumps([{"name": name, "value": str(value)} for name, value in zip(
            age.ROLES, (100, returned, returned, f"11/{day:02d} 09:10 AM MST", early, returned + early))]).encode(),
        age.CHART + "lYjhf/embed.js": json.dumps(embed, separators=(",", ":")).encode(),
        base + "dataset.csv": ("AgeBin,abs,ev,n\n" + "".join(
            f"{group},{returned // 5},{early // 5},{(returned + early) // 5}\n" for group in age.AGES)).encode(),
    }


class Collector:
    now = datetime(2026, 11, 21, tzinfo=timezone.utc)
    offline = False

    def __init__(self, bodies, prior=None):
        self.bodies = bodies
        self.prior = {age.FEED: prior} if prior else {}

    def acquire(self, url):
        return self.bodies[url], None

    def observation_time(self):
        return self.now

    def capture(self, feed, url, parse, *, equivalent):
        body = self.bodies[url]
        data = parse(body)
        return {"source": {"url": url, **pin(body)}, "data": data, "status": "reported"}


def test_verified_modes_replay_origins_and_keep_unchanged_pins():
    bodies = sources()
    entry = age.collect(Collector(bodies))
    rows = list(age.exports({age.FEED: entry}))
    assert len(rows) == 5 and sum(r["combined_source_reported_activity"] for r in rows) == 30
    assert entry["data"]["participation_observation_qualified"] is False
    for _, source, _, limit, allowed, parse, expected in age.original_reports({age.FEED: entry}):
        body = bodies[source["url"]]
        assert allowed and len(body) <= limit and parse(body) == expected
    assert age.collect(Collector(bodies, entry))["data"] is entry["data"]


@pytest.mark.parametrize("returned", [5, 15])
def test_accepts_upward_and_downward_revisions_only_in_new_editions(returned):
    prior = age.collect(Collector(sources()))
    assert age.collect(Collector(sources(version=77, day=6, returned=returned),
                                 prior))["data"]["control"]["returned"] == returned
    with pytest.raises(ValueError, match="without a new source edition"):
        age.collect(Collector(sources(returned=returned), prior))


def test_asynchronous_chart_control_revision_fails_closed():
    bodies = sources()
    bodies[age.CONTROL] = sources(returned=15)[age.CONTROL]
    with pytest.raises(ValueError, match="disagree with dashboard"):
        age.collect(Collector(bodies))
