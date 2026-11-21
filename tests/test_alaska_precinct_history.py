import csv
import io

import pytest

from scripts import alaska_precinct_history as ak


def test_source_fields_agree_across_offices_and_are_not_summed_over_candidates():
    def body(second=5):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["Pct_Id", "Precinct_name", "Aggregation_ID", "Contest_title", "Contest_Id", *ak.FIELDS])
        first = ["01-600", "01-600 Ketchikan", "", ak.OFFICES[0], "1", 10, 5, 5, 0, 0, 0, 0]
        writer.writerows([first, first, ["01-600", "01-600 Ketchikan", "", ak.OFFICES[1], "2",
                                         10, second, second, 0, 0, 0, 0]])
        return stream.getvalue().encode()

    assert ak.parse_units(body()) == [["01-600 Ketchikan", "01-600", 10, 5, 5, 0, 0, 0, 0]]
    with pytest.raises(ValueError, match="between contests"):
        ak.parse_units(body(6))


def test_complete_mode_roster_and_control_include_unallocated_ballots():
    rows = [["01-600 Ketchikan", "01-600", 10, 5, 5, 0, 0, 0, 0],
            [ak.OVERSEAS, "99-999", 2, 1, 0, 1, 0, 0, 0]]
    for district in range(1, 41):
        for mode in ak.MODE_NAMES:
            rows.append([f"District {district} - {mode}", "", 0, 0, 0, 0, 0, 0, 0])
    control = ["2", "2", "6", "12", "50.00", "11/30/2024 4:00:37 PM"]
    ak.validate(rows, control)
    with pytest.raises(ValueError, match="complete official statewide"):
        ak.validate(rows[:-1], control)
    with pytest.raises(ValueError, match="complete official statewide"):
        ak.validate(rows, ["2", "2", "7", "12", "58.33", control[-1]])
