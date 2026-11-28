# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Extraction + acceptance tests over the committed CPR workbook fixture
(tests/fixtures/CPR_DM_2026_AOUT_CLEANED.xlsx). Runs wherever openpyxl is
importable (it ships with frappe); skipped otherwise:

	python3 erpnext/custom_modules/facturation/tests/test_mensuelle_workbook.py -v

The acceptance: January's declared figures, months 1-4/6/8 Conforme against
RECAP, and DM 05 / DM 07 / DM 09 / DM 10 flagged.
"""

import pathlib
import sys
import types
import unittest

if "frappe" not in sys.modules:
	try:
		import frappe  # noqa: F401
	except ImportError:
		_repo_root = str(pathlib.Path(__file__).resolve().parents[4])
		if _repo_root not in sys.path:
			sys.path.insert(0, _repo_root)
		_frappe = types.ModuleType("frappe")
		_frappe._ = lambda value, *a, **kw: value
		_utils = types.ModuleType("frappe.utils")
		_utils.cstr = lambda value: str(value) if value is not None else ""
		_frappe.utils = _utils
		sys.modules["frappe"] = _frappe
		sys.modules["frappe.utils"] = _utils
else:
	if not hasattr(sys.modules["frappe"], "_"):
		sys.modules["frappe"]._ = lambda value, *a, **kw: value

_repo_root = str(pathlib.Path(__file__).resolve().parents[4])
if _repo_root not in sys.path:
	sys.path.insert(0, _repo_root)

try:
	import openpyxl
except ImportError:
	openpyxl = None

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "CPR_DM_2026_AOUT_CLEANED.xlsx"

from erpnext.custom_modules.facturation import mensuelle_checks, mensuelle_workbook
from erpnext.custom_modules.facturation.mensuelle_checks import STATUS_CONFORME, STATUS_ECARTS


@unittest.skipIf(openpyxl is None or not FIXTURE.exists(), "openpyxl ou fixture absent")
class TestWorkbookExtraction(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.payload = mensuelle_workbook.extract_workbook(str(FIXTURE))
		cls.by_month = {}
		for sheet in cls.payload["sheets"]:
			month = mensuelle_workbook.parse_sheet_month(sheet["sheet"])
			cls.by_month[month] = sheet

	def test_monthly_sheets_and_ignored_sheets(self):
		self.assertEqual(sorted(self.by_month), list(range(1, 11)))
		ignored = [name for name in openpyxl.load_workbook(str(FIXTURE), read_only=True).sheetnames
			if mensuelle_workbook.is_ignored_sheet(name)]
		self.assertEqual(sorted(ignored), ["Feuil1", "Feuille 2"])

	def test_layout_profiles(self):
		# DM 01-06 use the older layout, DM 07-10 the newer one — whatever the
		# sheet-name case or trailing spaces
		self.assertEqual({m: self.by_month[m]["layout"] for m in range(1, 7)},
			{m: mensuelle_workbook.LAYOUT_LEGACY for m in range(1, 7)})
		self.assertEqual({m: self.by_month[m]["layout"] for m in range(7, 11)},
			{m: mensuelle_workbook.LAYOUT_RECENT for m in range(7, 11)})

	def test_header_digits_and_tax_id(self):
		january = self.by_month[1]
		self.assertEqual(january["month"], "01")
		self.assertEqual(january["year"], "2026")
		self.assertEqual(january["tax_id"], "1049028G")
		october = self.by_month[10]
		self.assertEqual(october["month"], "10")
		self.assertEqual(october["year"], "2026")

	def test_no_formula_without_cached_value(self):
		# every mapped cell with a formula must carry a cached value, else the
		# extraction flags "open and re-save in Excel"
		for sheet in self.payload["sheets"]:
			self.assertEqual(sheet["errors"], [], msg=f"{sheet['sheet']}: {sheet['errors']}")

	def test_january_declared_figures(self):
		january = self.by_month[1]["figures"]

		def value(key):
			return january[key]["value"]

		self.assertAlmostEqual(value("ht7"), 1092.760, places=3)
		self.assertAlmostEqual(value("tva7"), 76.493, places=3)
		self.assertAlmostEqual(value("ht19"), 129891.826, places=3)
		self.assertAlmostEqual(value("tva19"), 24679.447, places=3)
		self.assertAlmostEqual(value("tva_deductible"), 22471.865, places=3)
		self.assertAlmostEqual(value("timbre"), 370.0, places=3)
		self.assertAlmostEqual(value("tva_due"), 2284.075, places=3)
		self.assertAlmostEqual(value("tcl"), 311.481, places=3)
		self.assertAlmostEqual(value("gross"), 13654.922, places=3)
		self.assertAlmostEqual(value("irpp"), 2126.599, places=3)
		self.assertAlmostEqual(value("css"), 57.639, places=3)
		self.assertAlmostEqual(value("tfp"), 273.098, places=3)
		self.assertAlmostEqual(value("foprolos"), 136.549, places=3)
		self.assertAlmostEqual(value("rs3"), 35.700, places=3)
		self.assertAlmostEqual(value("rs1"), 1606.484, places=3)
		self.assertAlmostEqual(value("total"), 7528.313, places=3)

	def test_recap_months(self):
		# both RECAP tables parsed: months 1-10 carry figures, 11-12 are the
		# workbook's zero rows
		self.assertEqual(sorted(self.payload["recap"]), list(range(1, 13)))


@unittest.skipIf(openpyxl is None or not FIXTURE.exists(), "openpyxl ou fixture absent")
class TestWorkbookAcceptance(unittest.TestCase):
	"""The full checks over the real workbook: months 1-4, 6, 8 Conforme
	against RECAP; DM 05 / 07 / 09 / 10 flagged."""

	@classmethod
	def setUpClass(cls):
		cls.payload = mensuelle_workbook.extract_workbook(str(FIXTURE))
		cls.results = {}
		for sheet in cls.payload["sheets"]:
			month = mensuelle_workbook.parse_sheet_month(sheet["sheet"])
			recap_row = cls.payload["recap"].get(month)
			cls.results[month] = mensuelle_checks.run_checks(sheet, recap_row, dm=None)

	def test_conforme_months(self):
		for month in (1, 2, 3, 4, 6, 8):
			self.assertEqual(
				self.results[month]["status"],
				STATUS_CONFORME,
				msg=f"mois {month:02d}: {self.results[month]['controls']}",
			)

	def test_dm05_stale_copy_is_ecarts(self):
		self.assertEqual(self.results[5]["status"], STATUS_ECARTS)
		self.assertIn("RECAP_TIMBRE", [c["check_code"] for c in self.results[5]["controls"]])

	def test_dm07_total_omits_tva_and_sales_lower_than_recap(self):
		self.assertEqual(self.results[7]["status"], STATUS_ECARTS)
		self.assertIn("TOTAL_CALC", [c["check_code"] for c in self.results[7]["controls"]])
		self.assertIn("RECAP_HT7", [c["check_code"] for c in self.results[7]["controls"]])

	def test_dm09_timbre_flagged(self):
		self.assertEqual(self.results[9]["status"], STATUS_ECARTS)
		timbre = next(c for c in self.results[9]["controls"] if c["check_code"] == "RECAP_TIMBRE")
		self.assertEqual((timbre["declare"], timbre["attendu"]), (410.0, 409.0))

	def test_dm10_totals_and_deductible_flagged(self):
		self.assertEqual(self.results[10]["status"], STATUS_ECARTS)
		self.assertIn("RECAP_TVA_DUE", [c["check_code"] for c in self.results[10]["controls"]])
		self.assertIn("RECAP_TVA_DEDUCTIBLE", [c["check_code"] for c in self.results[10]["controls"]])


@unittest.skipIf(openpyxl is None or not FIXTURE.exists(), "openpyxl ou fixture absent")
class TestSheetCopy(unittest.TestCase):
	def test_values_only_single_sheet_copy(self):
		content = mensuelle_workbook.build_sheet_copy(str(FIXTURE), "DM 01")
		import io

		wb = openpyxl.load_workbook(io.BytesIO(content), data_only=False)
		self.assertEqual(wb.sheetnames, ["DM 01"])
		formulas = [
			cell.value
			for row in wb["DM 01"].iter_rows()
			for cell in row
			if isinstance(cell.value, str) and cell.value.startswith("=")
		]
		self.assertEqual(formulas, [])
		# values carry the cached numbers, styles and merges survive
		self.assertAlmostEqual(wb["DM 01"]["A17"].value, 2126.599, places=3)
		self.assertAlmostEqual(wb["DM 01"]["P76"].value, 7528.313452, places=4)
		self.assertTrue(wb["DM 01"].merged_cells.ranges, "les cellules fusionnees doivent rester")


if __name__ == "__main__":
	unittest.main()
