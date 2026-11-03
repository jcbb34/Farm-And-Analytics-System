import unittest

from app.services.csv_safety import safe_csv_cell


class CsvSafetyTests(unittest.TestCase):
    def test_formula_like_text_is_neutralized(self):
        self.assertEqual(safe_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(safe_csv_cell("  @SUM(A1:A2)"), "'  @SUM(A1:A2)")

    def test_normal_values_are_unchanged(self):
        self.assertEqual(safe_csv_cell("Native Pig"), "Native Pig")
        self.assertEqual(safe_csv_cell(25.5), 25.5)


if __name__ == "__main__":
    unittest.main()
