# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for the portal receipt logic
(declaration_portal.py): the echeance rule (20th / 28th of the following
month, December rollover), the non-working-day warning (weekend or fixed
Tunisian public holiday) and the per-impot amount mapping. Run from the app
root: python3 erpnext/custom_modules/entries/tests/test_declaration_portal.py -v
"""

import pathlib
import sys
import types
import unittest
from datetime import date

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

from erpnext.custom_modules.entries.declaration_portal import (
	ECHEANCE_DAY_OTHER,
	ECHEANCE_DAY_TELEDECLARE,
	calculated_impot_amounts,
	compute_echeance,
	declared_impot_amounts,
	echeance_with_warning,
	is_tunisian_public_holiday,
	is_working_day,
	next_working_day,
	portal_line_totals,
)


class TestEcheanceRule(unittest.TestCase):
	def test_january_2026_teledeclaration_is_feb_20(self):
		self.assertEqual(compute_echeance(2026, 1, teledeclaration=True), date(2026, 2, 20))
		self.assertEqual(ECHEANCE_DAY_TELEDECLARE, 20)

	def test_january_2026_without_teledeclaration_is_feb_28(self):
		self.assertEqual(compute_echeance(2026, 1, teledeclaration=False), date(2026, 2, 28))
		self.assertEqual(ECHEANCE_DAY_OTHER, 28)

	def test_december_rolls_into_next_january(self):
		self.assertEqual(compute_echeance(2026, 12, teledeclaration=True), date(2027, 1, 20))
		self.assertEqual(compute_echeance(2026, 12, teledeclaration=False), date(2027, 1, 28))

	def test_invalid_month_raises(self):
		with self.assertRaises(ValueError):
			compute_echeance(2026, 13)


class TestWorkingDays(unittest.TestCase):
	def test_weekend_warning(self):
		# August's declaration pays by September 20 2026 — a Sunday: the
		# warning names Monday the 21st
		self.assertEqual(date(2026, 9, 20).weekday(), 6)
		echeance, warning = echeance_with_warning(2026, 8, teledeclaration=True)
		self.assertEqual(echeance, date(2026, 9, 20))
		self.assertIsNotNone(warning)
		self.assertIn("21/09/2026", warning)

	def test_public_holiday_warning(self):
		# February's echeance lands on March 20 — the Independence Day holiday
		self.assertTrue(is_tunisian_public_holiday(date(2026, 3, 20)))
		echeance, warning = echeance_with_warning(2026, 2, teledeclaration=True)
		self.assertEqual(echeance, date(2026, 3, 20))
		self.assertIsNotNone(warning)
		self.assertIn("23/03/2026", warning)

	def test_working_echeance_has_no_warning(self):
		# January 2026: the 20th of February is a Friday
		self.assertEqual(date(2026, 2, 20).weekday(), 4)
		echeance, warning = echeance_with_warning(2026, 1, teledeclaration=True)
		self.assertEqual(echeance, date(2026, 2, 20))
		self.assertIsNone(warning)

	def test_next_working_day_skips_the_weekend(self):
		self.assertEqual(next_working_day(date(2026, 2, 28)), date(2026, 3, 2))


class TestImpotAmounts(unittest.TestCase):
	def test_declared_amounts_lump_the_rs_family(self):
		rubriques = [
			{"code": "F1_1", "montant": 2126.599},
			{"code": "F1_3", "montant": 57.639},
			{"code": "F1_4_1", "montant": 326.6876},
			{"code": "F1_6", "montant": 35.7},
			{"code": "F1_17_1", "montant": 1606.484},
			{"code": "F2_1", "montant": 273.09844},
			{"code": "F3_1", "montant": 136.54922},
			{"code": "F5_1_1", "montant": 76.4932},
			{"code": "F5_1_3", "montant": 24679.44694},
			{"code": "F5_2_4", "montant": 22471.865},
			{"code": "F7", "montant": 370.0},
			{"code": "F9_3_1", "montant": 311.4810523},
			{"code": "TOTAL", "montant": 7528.313452},
		]
		amounts = declared_impot_amounts(rubriques)
		# RS = the whole F1_* family
		self.assertEqual(amounts["rs"], 4153.11)
		self.assertEqual(amounts["tfp"], 273.09844)
		self.assertEqual(amounts["foprolos"], 136.54922)
		# the TVA position: collected (7% + 19%) - deductible, at 3 decimals
		self.assertEqual(amounts["tva"], 2284.075)
		self.assertEqual(amounts["timbre"], 370.0)
		self.assertEqual(amounts["tcl"], 311.481)
		self.assertIsNone(amounts["reliquat"])

	def test_calculated_amounts_come_from_the_dm_totals(self):
		dm = {
			"total_rs": 4153.11, "total_tfp": 273.098, "total_foprolos": 136.549,
			"tva_a_payer": 2284.075, "total_timbre": 370.0, "total_tcl": 311.481,
		}
		amounts = calculated_impot_amounts(dm)
		self.assertEqual(amounts["rs"], 4153.11)
		self.assertEqual(amounts["tva"], 2284.075)
		self.assertIsNone(amounts["reliquat"])
		self.assertEqual(calculated_impot_amounts(None)["rs"], None)

	def test_portal_line_totals(self):
		portal = {
			"lines": [
				{"impot": "Retenue a la Source", "total": 4153.109},
				{"impot": "TFP", "total": 273.098},
				{"impot": "FOPROLOS", "total": 136.549},
				{"impot": "TVA", "total": 2284.074},
				{"impot": "Droit de timbre", "total": 370.0},
				{"impot": "TCL", "total": 311.481},
				{"impot": "Reliquat minimum de perception", "total": 0.0},
			]
		}
		totals = portal_line_totals(portal)
		self.assertEqual(totals["rs"], 4153.109)
		self.assertEqual(totals["tva"], 2284.074)
		self.assertEqual(totals["reliquat"], 0.0)
		self.assertIsNone(portal_line_totals(None)["tva"])


if __name__ == "__main__":
	unittest.main()
