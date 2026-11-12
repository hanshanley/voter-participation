import io
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile

from scripts.historical_state_products import (
    PA_FIELDS, alabama_rows, kansas_rows, pennsylvania_rows)


class HistoricalStateTests(unittest.TestCase):
    def test_pennsylvania_codes_and_yes_no_counts_are_not_reinterpreted_as_ballots(self):
        source={key:"" for key in PA_FIELDS}
        source.update(election_year="2018",election_type="G",county_code="2",precinct_code="000010",
            candidate_last_name="Candidate",candidate_office_code="USH",candidate_party_code="DEM",
            vote_total="-2",yes_vote_total="3",no_vote_total="4",fips_code="003")
        import csv
        text=io.StringIO(newline="")
        csv.writer(text).writerow([source[key] for key in PA_FIELDS])
        rows=list(pennsylvania_rows(text.getvalue().encode(),2018,
            b"Requested Year 2018\nRecord Count: 1\n"))
        self.assertEqual(rows[0]["count_status"],"negative_correction")
        self.assertEqual(rows[0]["county_literal"],"2")
        self.assertEqual(rows[0]["unit_literal"],"000010")
        self.assertEqual(json.loads(rows[0]["source_fields_json"]),source)
        self.assertNotEqual(rows[0]["measure"],"ballots_cast")

    def test_pennsylvania_documented_record_count_is_enforced(self):
        values=["2018","G"]+[""]*(len(PA_FIELDS)-2)
        body=(",".join(values)+"\n").encode()
        with self.assertRaises(ValueError):
            list(pennsylvania_rows(body,2018,b"Requested Year 2018\nRecord Count: 2\n"))

    def test_kansas_county_supplement_is_preserved_not_added_twice(self):
        import openpyxl
        wb=openpyxl.Workbook()
        long=wb.active;long.title="PRECINCT"
        long.append(["County","Precinct","Race","Candidate","Party","Votes","VTD"])
        long.append(["ALLEN","001","US House 2","Candidate","Republican",0,"000010"])
        other=wb.create_sheet("JOHNSON")
        other.append(["PRECINCT CODE","CANDIDATE"])
        other.append(["001",99])
        body=io.BytesIO();wb.save(body);wb.close()
        grids=io.StringIO()
        rows=list(kansas_rows(body.getvalue(),grids))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["count_literal"],"0")
        self.assertEqual(json.loads(rows[0]["source_fields_json"])["VTD"],"000010")
        self.assertIn('"sheet": "JOHNSON"',grids.getvalue())
        self.assertIn("99",grids.getvalue())

    def test_alabama_native_ballots_and_placeholder_registration_stay_distinct(self):
        import xlrd
        values=[
            ["Contest Title","Party","Candidate","001","ABSENTEE"],
            ["REGISTERED VOTERS - TOTAL"," ","Registered Voters",0,0],
            ["BALLOTS CAST - TOTAL"," ","Ballots",7,2],
            ["US HOUSE","REP","Candidate",6,1]]
        sheet=SimpleNamespace(name="Precinct Results",nrows=4,ncols=5,
            row_values=lambda r:values[r],cell_value=lambda r,c:values[r][c],
            cell=lambda r,c:SimpleNamespace(value=values[r][c],ctype=xlrd.XL_CELL_NUMBER))
        workbook=SimpleNamespace(sheets=lambda:[sheet],release_resources=lambda:None)
        body=io.BytesIO()
        with zipfile.ZipFile(body,"w") as archive:
            archive.writestr("2018-General-Test.xls",b"fixture")
        with patch("xlrd.open_workbook",return_value=workbook):
            rows=list(alabama_rows(body.getvalue(),2018))
        self.assertEqual([row["measure"] for row in rows],
            ["registration_stock"]*2+["ballots_cast"]*2+["native_contest_or_administrative_value"]*2)
        self.assertEqual(rows[0]["count_literal"],"0")
        self.assertIn("not_qualified_denominators",rows[0]["qualification"])
        self.assertEqual(rows[3]["unit_kind"],"pooled_administrative_unit")


if __name__=="__main__":
    unittest.main()
