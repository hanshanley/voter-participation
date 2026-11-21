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


@pytest.mark.parametrize("first,rate", [(52, "50.05%"), (50, "50.00%"), (48, "49.95%")])
def test_current_unit_revisions_require_literal_json_and_pdf_controls(first, rate):
    rows = [[f"01-{i:03d} Name {i}", f"01-{i:03d}", 10, 5, 5, 0, 0, 0, 0] for i in range(402)]
    rows[0][2:5] = [100, first, first]
    precincts = sorted([identity, label[len(identity) + 1:], ballots, registered]
                       for label, identity, registered, ballots, *_ in rows)
    rows += [[ak.OVERSEAS, "99-999", 2, 1, 0, 1, 0, 0, 0]]
    for district in range(1, 41):
        for mode in ak.MODE_NAMES:
            rows.append([f"District {district} - {mode}", "", 0, 0, 0, 0, 0, 0, 0])
    total, registered = sum(row[3] for row in rows), sum(row[2] for row in rows)
    pdf = {"page_clocks_and_ordinals": [["11/18/2026 5:25:35 PM", "1", "1"]],
           "statewide_header": ["401", "401", "100.00%", str(total), str(registered), rate, ak.current.STATUS[0]]}
    native = {"updated": "11/18/2026 5:56 PM", "certified": False,
              "federal_controls": [{"office": office, "b": total, "v": registered, "p": 403, "r": 401}
                                   for office in ak.current.OFFICES]}
    assert ak.current_reconcile(rows, pdf, native, precincts)["voters"] == total
    precincts[0][2] += 1
    with pytest.raises(ValueError, match="literal native roster"):
        ak.current_reconcile(rows, pdf, native, precincts)
