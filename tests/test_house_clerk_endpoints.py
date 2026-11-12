import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "house_clerk", Path(__file__).resolve().parents[1] / "scripts/house_clerk_endpoints.py")
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


def line(text, page=1, x=45, y=100):
    words = text.split()
    return dict(page=page, x=x, y=y, text=text,
                words=[dict(x0=550 if i == len(words)-1 else x+i*4,
                            y0=y, x1=580, y1=y+8, text=word)
                       for i, word in enumerate(words)])


class CandidateEndpointTests(unittest.TestCase):
    def test_explicit_fusion_lines_follow_the_same_nominee(self):
        source = [
            line("CONNECTICUT"), line("FOR UNITED STATES REPRESENTATIVE"),
            line("1. Jane Candidate, Democrat ........ 100"),
            line("Working Families ........ 20", x=75),
            line("Pat Candidate, Republican ........ 90"),
        ]
        rows, ignored = model.candidate_lines(source)
        candidates = model.candidate_totals(rows)
        self.assertEqual(ignored, [])
        self.assertEqual([(r["counted_as"], r["votes"]) for r in candidates],
                         [("D", 120), ("R", 90)])
        self.assertEqual(rows[1]["literal_party"], "Working Families")

    def test_blank_and_continuing_ballots_are_not_other_candidates(self):
        source = [
            line("MAINE"), line("FOR UNITED STATES REPRESENTATIVE"),
            line("1. Jane Candidate, Democrat ........ 100"),
            line("Pat Candidate, Republican ........ 90"),
            line("Blank ........ 4"), line("Continuing Ballots ........ 190"),
            line("Exhausted Ballots ........ 8"), line("Write-in ........ 0"),
        ]
        rows, ignored = model.candidate_lines(source)
        self.assertEqual([r["votes"] for r in ignored], [4, 190, 8])
        self.assertEqual([r["votes"] for r in rows], [100, 90, 0])
        self.assertEqual(rows[-1]["role"], "source_unassigned_write_in")

    def test_mixed_minor_and_major_affiliation_is_explicit(self):
        rows, _ = model.candidate_lines([
            line("VERMONT"), line("FOR UNITED STATES REPRESENTATIVE"), line("AT LARGE"),
            line("Pat Candidate, Republican, Libertarian ........ 104"),
            line("Jane Candidate, Democrat ........ 218"),
        ])
        candidates = model.candidate_totals(rows)
        self.assertEqual({r["candidate"]: (r["counted_as"], r["votes"]) for r in candidates},
                         {"Pat Candidate": ("R", 104), "Jane Candidate": ("D", 218)})

    def test_page_change_cannot_leak_into_a_recapitulation(self):
        rows, _ = model.candidate_lines([
            line("ALASKA"), line("FOR UNITED STATES REPRESENTATIVE"), line("AT LARGE"),
            line("Jane Candidate, Democrat ........ 100"),
            line("Libertarian", page=2),
        ])
        self.assertEqual(len(rows), 1)

    def test_named_write_in_slogans_and_footnotes_stay_literal(self):
        rows, _ = model.candidate_lines([
            line("OKLAHOMA"), line("FOR UNITED STATES REPRESENTATIVE"),
            line("1. Person, Jr., Write-in (Independent) ........ 0"),
            line("Another Person, All Of Us! ........ 8"),
            line("2. Unopposed Person, Republican ........ (1)"),
        ])
        self.assertEqual(rows[0]["candidate"], "Person, Jr.")
        self.assertEqual(rows[0]["votes"], 0)
        self.assertEqual(rows[1]["literal_party"], "All Of Us!")
        self.assertIsNone(rows[2]["votes"])
        self.assertIsNone(model.candidate_totals(rows)[-1]["votes"])

    def test_ambiguous_major_affiliation_and_orphan_fusion_are_rejected(self):
        with self.assertRaises(ValueError):
            model.candidate_totals([dict(district="CT-01", candidate="Same Person",
                state_code="CT", parent_affiliations=["Democrat", "Republican"], votes=10,
                role="named_candidate")])
        with self.assertRaises(ValueError):
            model.candidate_lines([
                line("CONNECTICUT"), line("FOR UNITED STATES REPRESENTATIVE"),
                line("1. Working Families ........ 20", x=75),
            ])


if __name__ == "__main__":
    unittest.main()
