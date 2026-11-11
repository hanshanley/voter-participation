import importlib
import tempfile
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

from scripts import civic_estimates as civic


class ReconstructionTests(unittest.TestCase):
    def test_import_preserves_callers_decimal_context(self):
        with localcontext() as context:
            context.prec = 37
            importlib.reload(civic)
            self.assertEqual(context.prec, 37)

    def test_both_switch_directions_have_factor_two(self):
        self.assertEqual(civic.component("R", "D"), ("switching", 2))
        self.assertEqual(civic.component("D", "R"), ("switching", -2))

    def test_nonparticipation_not_unknown(self):
        self.assertEqual(civic.component("D", "N"), ("modeled_nonparticipation", -1))
        self.assertEqual(civic.component("R", "N"), ("modeled_nonparticipation", 1))
        self.assertEqual(civic.component("R", "U"), ("unresolved", 1))

    def test_entry_not_switching(self):
        self.assertEqual(civic.component("N", "D"), ("no_prior_contest_vote_entry", 1))
        self.assertEqual(civic.component("N", "R"), ("no_prior_contest_vote_entry", -1))

    def test_other_is_not_nonparticipation(self):
        self.assertEqual(civic.component("D", "O"), ("other_choice", -1))
        self.assertEqual(civic.component("O", "D"), ("other_choice", 1))

    def test_every_transition_reconciles(self):
        cells = {(p, c): Decimal(i + 1) / 8 for i, (p, c) in enumerate(
            (p, c) for p in "DRONU" for c in "DRONU")}
        result = civic.decomposition(cells)
        self.assertLess(abs(sum(result[n] for n in civic.COMPONENTS)
                            - result["m26"] + result["m24"]), Decimal("1e-20"))

    def test_decimal_serialization_normalization(self):
        self.assertEqual(civic.code("1.0"), "1")
        self.assertEqual(civic.code("88"), "88")
        self.assertEqual(civic.code(""), "MISSING")
        with self.assertRaises(ValueError):
            civic.code("1.5")

    def test_unknown_remains_in_margin_accounting(self):
        result = civic.decomposition({("D", "U"): Decimal(2), ("U", "R"): Decimal(3)})
        self.assertEqual(result["unresolved"], -5)
        self.assertEqual(result["modeled_nonparticipation"], 0)

    def test_denominator_component_is_required(self):
        result = civic.decomposition({("D", "D"): Decimal(5), ("R", "N"): Decimal(5)})
        scale = (1 / result["t24"] + 1 / result["t26"]) / 2
        raw_scaled = sum(result[n] for n in civic.COMPONENTS) * scale
        denom = (result["m24"] + result["m26"]) / 2 * (1 / result["t26"] - 1 / result["t24"])
        self.assertEqual(raw_scaled + denom, Decimal(1))
        self.assertNotEqual(raw_scaled, Decimal(1))

    def test_private_output_rejects_git_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            with self.assertRaises(ValueError):
                civic.private_destination(root / "public" / "fine-cells")

    def test_private_output_rejects_worktree_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "checkout"
            checkout.mkdir()
            (checkout / ".git").write_text("gitdir: elsewhere\n")
            alias = root / "alias"
            alias.symlink_to(checkout, target_is_directory=True)
            with self.assertRaises(ValueError):
                civic.private_destination(alias / "fine-cells")
            self.assertEqual(civic.private_destination(root / "private-results"),
                             (root / "private-results").resolve())


if __name__ == "__main__":
    unittest.main()
