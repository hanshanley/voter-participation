import gzip
import json

import pytest

from scripts import audit_louisiana_precinct_reference as reference


def test_native_parish_identity_is_resolved_by_name_and_child_counts_reconcile():
    def row(level, native_id, n, county="DE SOTO"):
        return {
            "election": {"date": reference.ELECTION},
            "measure": {"literal": "# VOTING"},
            "view": {
                "participation_measure_kind": "voters_reported", "source_mode": "all_methods",
                "geography_level": level, "county": county, "ballots": n, "denominator": None,
                "unit_key": native_id, "source_url": reference.SOURCE, "source_sha256": "a" * 64,
                "native_record": {"native_id": native_id, "voters_participating": n},
            },
        }

    snapshot = {
        "state_code": "LA", "year": 2026,
        "records": [
            row("state", "STATE", 15),
            row("county_equivalent", "PAR 77", 15),
            row("precinct", "PAR 77 W 02 P 001A", 10),
            row("precinct", "PAR 77 W 02 P 001B", 5),
        ],
    }

    def read():
        return reference.participation(gzip.compress(json.dumps(snapshot).encode()), {"DESOTO": "22031"})

    children, _ = read()
    assert children["22031"] == [("PAR 77 W 02 P 001A", "PAR 77", "2-1A", 10),
                                 ("PAR 77 W 02 P 001B", "PAR 77", "2-1B", 5)]
    snapshot["records"][3] = row("precinct", "PAR 77 W 02 P 001A", 5)
    with pytest.raises(ValueError, match="Precinct roster"):
        read()
    snapshot["records"][3] = row("precinct", "PAR 77 W 02 P 001B", 4)
    with pytest.raises(ValueError, match="parish counts do not reconcile"):
        read()
