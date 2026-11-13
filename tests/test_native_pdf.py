import unittest

import fitz

from scripts.native_pdf import count, grid, project, read, text


class NativePdfTests(unittest.TestCase):
    def test_native_zero_and_blank_remain_distinct(self):
        with fitz.open() as document:
            page = document.new_page(width=200, height=100)
            page.insert_text((20, 40), "0", fontsize=10)
            facts = read(document.tobytes())["pages"][0]
        cells = grid(facts, [(20, 50)], [(10, 50), (50, 90)])[0]
        self.assertEqual(count(cells[0]), dict(value=0, native_status="reported", native_text="0"))
        self.assertEqual(count(cells[1]), dict(value=None, native_status="blank", native_text=""))

    def test_touching_native_numbers_are_selected_by_cell_not_whitespace(self):
        with fitz.open() as document:
            page = document.new_page(width=200, height=100)
            page.insert_text((10, 40), "12", fontsize=10)
            page.insert_text((22, 40), "34", fontsize=10)
            facts = read(document.tobytes())["pages"][0]
        cells = grid(facts, [(20, 50)], [(0, 21.5), (21.5, 40)])[0]
        self.assertEqual([count(cell)["value"] for cell in cells], [12, 34])
        self.assertEqual("".join(glyph["text"] for glyph in facts["glyphs"]), "1234")

    def test_rotation_keeps_native_and_reading_coordinates(self):
        with fitz.open() as document:
            page = document.new_page(width=200, height=100)
            page.insert_text((10, 40), "731", fontsize=10)
            page.set_rotation(90)
            facts = read(document.tobytes())["pages"][0]
        self.assertEqual(facts["native_rotation"], 90)
        self.assertEqual(facts["reading_rect"], [0, 0, 100, 200])
        self.assertTrue(all(glyph["native_bbox"] != glyph["reading_bbox"] for glyph in facts["glyphs"]))
        self.assertEqual(len(facts["glyphs"]), 3)

    def test_separate_values_missing_source_and_overlapping_bands_fail_closed(self):
        with fitz.open() as document:
            page = document.new_page(width=200, height=100)
            page.insert_text((10, 40), "12", fontsize=10)
            page.insert_text((50, 40), "34", fontsize=10)
            facts = read(document.tobytes())["pages"][0]
        with self.assertRaises(ValueError):
            count(text(facts, [0, 20, 90, 50]))
        with self.assertRaises(ValueError):
            grid(facts, [(20, 50)], [(0, 40), (30, 60)])
        with fitz.open() as document:
            document.new_page()
            empty = read(document.tobytes())["pages"][0]
        self.assertTrue(empty["native_text_absent_requires_separate_review"])
        with self.assertRaises(ValueError):
            grid(empty, [(20, 50)], [(0, 40)])

    def test_signed_native_discrepancy_is_preserved_only_when_explicitly_requested(self):
        cell = dict(decoded_text="-1")
        with self.assertRaises(ValueError):
            count(cell)
        self.assertEqual(count(cell, allow_negative=True),
            dict(value=-1, native_status="reported", native_text="-1"))

    def test_nonzero_media_origin_and_crop_preserve_grid_registration(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), fitz.open() as document:
                page = document.new_page(width=612, height=792)
                page.set_mediabox(fitz.Rect(-12, 12, 600, 804))
                page.draw_rect(fitz.Rect(80, 100, 300, 200))
                page.draw_line((200, 100), (200, 200))
                page.draw_line((80, 150), (300, 150))
                page.set_cropbox(fitz.Rect(50, 50, 550, 750))
                page.set_rotation(rotation)
                expected = fitz.Rect(18, 50, 238, 150) * page.rotation_matrix
                facts = read(document.tobytes())["pages"][0]
            self.assertEqual(len(facts["detected_tables"]), 1)
            for actual, wanted in zip(facts["detected_tables"][0]["bbox"], expected):
                self.assertAlmostEqual(actual, wanted, places=3)

    def test_pdf_user_units_do_not_shift_cells_between_readers(self):
        with fitz.open() as document:
            page = document.new_page(width=200, height=100)
            page.draw_rect(fitz.Rect(10, 10, 90, 70))
            page.draw_line((50, 10), (50, 70))
            page.draw_line((10, 40), (90, 40))
            page.insert_text((20, 30), "731", fontsize=8)
            document.xref_set_key(page.xref, "UserUnit", "2")
            facts = read(document.tobytes())["pages"][0]
        self.assertEqual(facts["detected_tables"][0]["bbox"], [20, 20, 180, 140])
        first = facts["detected_tables"][0]["rows"][0][0]
        self.assertEqual(count(text(facts, first))["value"], 731)

    def test_changed_header_or_unsupported_measure_cannot_be_silently_projected(self):
        with fitz.open() as document:
            page = document.new_page(width=200, height=100)
            page.insert_text((10, 20), "Ballots tallied", fontsize=8)
            page.insert_text((10, 40), "731", fontsize=8)
            facts = read(document.tobytes())
        spec = dict(id="ballots", page=1, source_role="unqualified_native_facts",
            require=[dict(reading_bbox=[0, 0, 100, 25], decoded_text="Ballots tallied")],
            fields=[dict(id="tallied", kind="count", band=[0, 100])], rows=[[25, 50]])
        self.assertEqual(project(facts, spec)["rows"][0]["cells"]["tallied"]["value"], 731)
        spec["require"][0]["decoded_text"] = "Ballots issued"
        with self.assertRaises(ValueError):
            project(facts, spec)
        spec["require"][0]["decoded_text"] = "Ballots tallied"
        spec["fields"][0]["kind"] = "repaired_count"
        with self.assertRaises(ValueError):
            project(facts, spec)


if __name__ == "__main__":
    unittest.main()
