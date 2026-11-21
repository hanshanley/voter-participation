"""Shared registration for export-only participation products."""
from functools import partial

from scripts import (
    alabama_precinct_history, alaska_age_history, alaska_cards_history, alaska_precinct_history,
    connecticut_turnout_history, national_turnout_release_watch, oregon_turnout_history,
    southeast_turnout, washington_participation,
)


def routes(module, feeds):
    return {feed: partial(module.collect, feed=feed) for feed in feeds}


def families():
    """Each family declares its routes, weekly reuse policy, and download schemas."""
    watch, wa, oregon, se = national_turnout_release_watch, washington_participation, oregon_turnout_history, southeast_turnout
    al, ak = alabama_precinct_history, alaska_precinct_history
    cards, age, ct = alaska_cards_history, alaska_age_history, connecticut_turnout_history
    return (
        (routes(watch, watch.INDEXES), True, (), None),
        ({wa.FEED: wa.collect}, True, (wa.CSV,), wa.exports),
        (routes(oregon, oregon.URLS), True, (oregon.CSV,), oregon.exports),
        (routes(se, se.URLS), True, (se.SC_CSV, se.AL_CSV), se.exports),
        (routes(al, al.URLS), True, (al.CSV, al.CONTROL_CSV), al.exports),
        ({ak.FEED: ak.collect}, True, (ak.CSV,), ak.exports),
        ({ak.CURRENT_FEED: ak.collect_current}, False, (ak.CURRENT_CSV,), ak.current_exports),
        (routes(cards, cards.ROUTES), True, (cards.CSV,), cards.exports),
        (routes(age, age.YEARS), True, (age.CSV,), age.exports),
        (routes(ct, ct.FEEDS), True, (ct.CSV,), ct.exports),
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
