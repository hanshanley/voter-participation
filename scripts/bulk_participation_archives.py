"""Shared registration for export-only participation products."""
from functools import partial
import re

from scripts import (
    alabama_precinct_history, alaska_age_history, alaska_cards_history, alaska_precinct_history, california_media,
    connecticut_turnout_history, dakota_turnout_history, hawaii_turnout_history, kansas_turnout_history,
    national_turnout_release_watch, new_jersey_periodic_counties, north_carolina_participation, oregon_turnout_history,
    southeast_turnout, washington_participation,
)
from scripts.participation_intake.contract import pin


def routes(module, feeds):
    return {feed: partial(module.collect, feed=feed) for feed in feeds}


def families():
    """Each family declares its routes, weekly reuse policy, and download schemas."""
    watch, wa, oregon, se = national_turnout_release_watch, washington_participation, oregon_turnout_history, southeast_turnout
    al, ak = alabama_precinct_history, alaska_precinct_history
    cards, age, ct = alaska_cards_history, alaska_age_history, connecticut_turnout_history
    return (
        (routes(watch, (watch.CENSUS, watch.EAC, watch.CT)), True, (watch.CSV,), watch.exports),
        (routes(watch, (watch.WV,)), True, (watch.FEDERAL_CSV,), watch.federal_exports),
        ({wa.FEED: wa.collect}, True, (wa.CSV,), wa.exports),
        (routes(oregon, oregon.URLS), True, (oregon.CSV,), oregon.exports),
        (routes(se, se.URLS), True, (se.SC_CSV, se.AL_CSV), se.exports),
        (routes(al, al.URLS), True, (al.CSV, al.CONTROL_CSV), al.exports),
        ({ak.FEED: ak.collect}, True, (ak.CSV,), ak.exports),
        ({ak.CURRENT_FEED: ak.collect_current}, False, (ak.CURRENT_CSV,), ak.current_exports),
        (routes(cards, cards.ROUTES), True, (cards.CSV,), cards.exports),
        (routes(age, age.YEARS), True, (age.CSV,), age.exports),
        (routes(ct, ct.FEEDS), True, (ct.CSV,), ct.exports),
        ({kansas_turnout_history.FEED: kansas_turnout_history.collect}, True,
         (kansas_turnout_history.CSV,), kansas_turnout_history.exports),
        ({hawaii_turnout_history.FEED: hawaii_turnout_history.collect}, True,
         (hawaii_turnout_history.CSV,), hawaii_turnout_history.exports),
        (routes(dakota_turnout_history, dakota_turnout_history.URLS), True,
         (dakota_turnout_history.CSV,), dakota_turnout_history.exports),
        (routes(new_jersey_periodic_counties, new_jersey_periodic_counties.FEEDS), False,
         (new_jersey_periodic_counties.CSV,), new_jersey_periodic_counties.exports),
        (routes(north_carolina_participation, north_carolina_participation.FEEDS), True,
         (north_carolina_participation.COUNTIES, north_carolina_participation.GROUPS,
          north_carolina_participation.PRECINCTS), north_carolina_participation.exports),
        (routes(california_media, california_media.FEEDS), False,
         (california_media.TURNOUT_CSV, california_media.HOUSE_CSV), california_media.exports),
    )


def collectors(*, reuse_checked_week=False):
    sources = {}
    for feeds, weekly, _, _ in families():
        for feed, capture in feeds.items():
            if feed in sources:
                raise ValueError(f"Duplicate bulk participation source: {feed}")
            sources[feed] = partial(capture, reuse_checked_week=True) if weekly and reuse_checked_week else capture
    return sources


def exports(entries):
    seen = set()
    for _, _, files, query in families():
        if not files:
            continue
        tables = query(entries)
        if len(files) == 1:
            tables = (tables,)
        for file, rows in zip(files, tables, strict=True):
            if file in seen:
                raise ValueError(f"Duplicate bulk participation export: {file}")
            seen.add(file)
            yield file, rows


def original_reports(entries):
    from scripts import results_indiana_turnout as indiana, results_turnout_history as history

    age, ct = alaska_age_history, connecticut_turnout_history
    for year, feed in indiana.FEEDS.items():
        if (data := (entries.get(feed) or {}).get("data")) is not None:
            report = data["report"]
            facts = {key: value for key, value in data.items() if key != "report"}
            yield (feed, report, ".pdf", indiana.MAX_BYTES, indiana.report_route(report["url"]),
                   partial(indiana.parse, year=year), facts)
    ks = kansas_turnout_history
    if (entry := entries.get(ks.FEED)) and entry.get("data") is not None:
        report = entry["source"]
        yield ks.FEED, report, ".pdf", ks.MAX_BYTES, report["url"] == ks.URL, ks.parse, entry["data"]
    hi = hawaii_turnout_history
    if (entry := entries.get(hi.FEED)) and entry.get("data") is not None:
        report = entry["source"]
        yield hi.FEED, report, ".html", hi.MAX_BYTES, report["url"] == hi.URL, hi.parse, entry["data"]
    dakota = dakota_turnout_history
    for feed, url in dakota.URLS.items():
        if (entry := entries.get(feed)) and entry.get("data") is not None:
            report = entry["source"]
            yield (feed, report, dakota.EXTENSIONS[feed], dakota.MAX_BYTES, report["url"] == url,
                   partial(dakota.parse, feed=feed), entry["data"])
    nj = new_jersey_periodic_counties
    for feed, county in nj.FEEDS.items():
        if (data := (entries.get(feed) or {}).get("data")) is not None:
            report = data["report"]
            facts = {key: value for key, value in data.items() if key != "report"}
            yield (feed, report, ".pdf", nj.MAX_BYTES, bool(nj.report_identity(report["url"], county)),
                   partial(nj.parse, county=county, url=report["url"]), facts)
    nc = north_carolina_participation
    ca = california_media
    for feed in ca.FEEDS:
        if (data := (entries.get(feed) or {}).get("data")) is not None:
            for kind, report in data["reports"].items():
                source = report["source"]
                yield (f"{feed}-{kind}", source, ".txt", ca.MAX_BYTES,
                       source["url"] == ca.URLS[kind], partial(ca.parse, kind), report["facts"])
    for feed, election in nc.FEEDS.items():
        if (data := (entries.get(feed) or {}).get("data")) is not None:
            for kind, report in data["pair"].items():
                source = report["source"]
                yield (f"{feed}-{kind}", source, ".zip", nc.MAX_BYTES,
                       source["url"] == nc.report_url(kind, election),
                       partial(nc.extract, kind=kind, election=election), report["facts"])
            if (control := data["age_control"]) is not None:
                source = control["source"]
                if "group_facts" in control:
                    yield (f"{feed}-demographic-control", source, ".html", 2_000_000,
                           source["url"] == nc.CONTROLS.get(election.year),
                           partial(nc.published_controls, year=election.year),
                           {field: control[field] for field in ("facts", "group_facts")})
                else:
                    yield (f"{feed}-age-control", source, ".html", 2_000_000,
                           source["url"] == nc.CONTROLS.get(election.year),
                           partial(nc.age_control, year=election.year), control["facts"])
    for feed, year in age.YEARS.items():
        entry = entries.get(feed) or {}
        if entry.get("data") is not None:
            url = age.source(year)
            extension = ".pdf" if year >= 2008 else ".htm"
            yield (feed, entry["source"], extension, 1_000_000, entry["source"]["url"] == url,
                   partial(age.parse, year=year), entry["data"])
    for feed, year in ct.FEEDS.items():
        entry = entries.get(feed) or {}
        if (data := entry.get("data")) is not None:
            report = data["report"]
            limit = ct.SCAN_LIMIT if year == 2018 else ct.STATEMENT_LIMIT if year in ct.STATEMENTS else 2_000_000
            facts = {key: value for key, value in data.items() if key != "report"}
            yield feed, report, ".pdf", limit, ct.valid_link(report["url"], year), partial(ct.parse, year=year), facts
    for feed, profile in history.VOTINGWORKS_TOWNS.items():
        entry = entries.get(feed) or {}
        data = entry.get("data") or {}
        if not profile.scanned or "scan_evidence" not in data:
            continue
        report = data["report"]
        history.votingworks_town_controls(data, profile)

        def reextract(body, *, profile, url):
            candidate = history.votingworks_report(body, profile.town, url, scanned=True)
            history.votingworks_town_controls(candidate, profile)
            return candidate["complete_native_query"]

        yield (feed, report, ".pdf", history.VOTINGWORKS_MAX_BYTES,
               entry["source"]["url"] == profile.index and profile.permits_report(report["url"]),
               partial(reextract, profile=profile, url=report["url"]), data["complete_native_query"])


def original_inventory(entries):
    inventory = {}
    for feed, report, extension, limit, valid_url, _, _ in original_reports(entries):
        size = report["bytes"]
        if (not valid_url or type(size) is not int or not 0 < size <= limit
                or not re.fullmatch(r"[a-f0-9]{64}", report["sha256"])):
            raise ValueError(f"Invalid original bulk participation report pin: {feed}")
        inventory[feed] = {"filename": feed + extension, "url": report["url"],
                           "bytes": size, "sha256": report["sha256"]}
    return inventory


def verify_original_reports(entries, directory):
    inventory = original_inventory(entries)
    if not inventory:
        raise ValueError("This checkpoint contains no supported bulk participation originals")
    for feed, _, _, _, _, parse, retained in original_reports(entries):
        report = inventory[feed]
        with (directory / report["filename"]).open("rb") as stream:
            body = stream.read(report["bytes"] + 1)
        if pin(body) != {"bytes": report["bytes"], "sha256": report["sha256"]}:
            raise ValueError(f"Changed original bulk participation report: {feed}")
        extracted = parse(body)
        if feed in alaska_age_history.YEARS and alaska_age_history.YEARS[feed] in alaska_age_history.SCANNED:
            year = alaska_age_history.YEARS[feed]
            if alaska_age_history.scan_facts(retained["scan_evidence"], year) != retained:
                raise ValueError(f"Retained scan evidence differs from its accepted query: {feed}")
            # Compare accepted cells, not platform-dependent OCR diagnostics.
            extracted = {key: value for key, value in extracted.items() if key != "scan_evidence"}
            retained = {key: value for key, value in retained.items() if key != "scan_evidence"}
        if extracted != retained:
            raise ValueError(f"Bulk participation report extraction differs from the accepted query: {feed}")
    return len(inventory)
