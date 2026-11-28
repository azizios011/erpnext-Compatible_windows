# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for the Déclaration Mensuelle recap assembly
(declaration_recap_logic.py). Run OUTSIDE a site, from the app root:

	python3 erpnext/custom_modules/reports/tests/test_declaration_recap.py -v

The fixtures reuse the CPR workbook's declared figures (prompt 2) and the
ledger-computed January Declaration Transaction (prompt 1).
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

from erpnext.custom_modules.reports.declaration_recap_logic import (
	ECART_TOLERANCE,
	build_recap,
	blank_month_row,
	dashboard_aggregates,
	ecart_row,
	row_from_declaration,
	row_from_liquide,
	row_from_mensuelle,
	totals_row,
)


def dm_payload():
	"""The January Declaration Transaction (prompt 1's ledger computation)."""
	return {
		"name": "DM-CPR-EX2026-01-Principale",
		"status": "Depose",
		"lines": [
			{"code": "F1_1", "montant_brut": 13654.9, "retenu": 2126.599},
			{"code": "F1_3", "montant_brut": 0.0, "retenu": 57.639},
			{"code": "F1_4_1", "montant_brut": 3266.887, "retenu": 326.688},
			{"code": "F1_6", "montant_brut": 1190.0, "retenu": 35.7},
			{"code": "F1_17_1", "montant_brut": 160648.4, "retenu": 1606.484},
			{"code": "F2_1", "montant_brut": 13654.9, "retenu": 273.098},
			{"code": "F3_1", "montant_brut": 13654.9, "retenu": 136.549},
			{"code": "F5_1_1", "montant_brut": 1092.757, "retenu": 76.493},
			{"code": "F5_1_3", "montant_brut": 129891.826, "retenu": 24679.447},
			{"code": "F5_2_4", "montant_brut": 0.0, "retenu": 22471.865},
			{"code": "F7", "montant_brut": 0.0, "retenu": 370.0},
			{"code": "F9_3_1", "montant_brut": 155740.523, "retenu": 311.481},
		],
		"tva_collectee": 24755.94,
		"tva_deductible": 22471.865,
		"tva_a_payer": 2284.075,
		"credit_suivant": 0.0,
		"total_a_payer": 7528.313,
	}


def mensuelle_lignes():
	"""The January declared figures (prompt 2's import mapping)."""
	return [
		{"code_rubrique": "F1_1", "base_declaree": 13654.922, "montant_declare": 2126.599},
		{"code_rubrique": "F1_3", "base_declaree": None, "montant_declare": 57.639},
		{"code_rubrique": "F1_4_1", "base_declaree": 3266.886, "montant_declare": 326.6876},
		{"code_rubrique": "F1_6", "base_declaree": 1190.0, "montant_declare": 35.7},
		{"code_rubrique": "F1_17_1", "base_declaree": 160648.4, "montant_declare": 1606.484},
		{"code_rubrique": "F2_1", "base_declaree": 13654.922, "montant_declare": 273.09844},
		{"code_rubrique": "F3_1", "base_declaree": 13654.922, "montant_declare": 136.54922},
		{"code_rubrique": "F5_1_1", "base_declaree": 1092.76, "montant_declare": 76.4932},
		{"code_rubrique": "F5_1_3", "base_declaree": 129891.826, "montant_declare": 24679.44694},
		{"code_rubrique": "F5_2_4", "base_declaree": 119602.155, "montant_declare": 22471.865},
		{"code_rubrique": "F7", "base_declaree": 370.0, "montant_declare": 370.0},
		{"code_rubrique": "F9_3_1", "base_declaree": 155740.5261, "montant_declare": 311.4810523},
		{"code_rubrique": "S_IMPOS", "base_declaree": 12578.236, "montant_declare": None},
		{"code_rubrique": "TOTAL", "base_declaree": None, "montant_declare": 7528.313452},
	]


class TestMonthRows(unittest.TestCase):
	def test_blank_months_are_none_not_zero(self):
		row = blank_month_row(3)
		self.assertEqual(row["mois"], "03")
		for key, value in row.items():
			if key != "mois":
				self.assertIsNone(value)

	def test_calculated_row_maps_the_dm_lines(self):
		row = row_from_declaration(1, dm_payload())
		self.assertEqual(row["mois"], "01")
		self.assertEqual(row["ht7"], 1092.757)
		self.assertEqual(row["tva7"], 76.493)
		self.assertEqual(row["ht19"], 129891.826)
		self.assertEqual(row["tva19"], 24679.447)
		self.assertEqual(row["tcl"], 311.481)
		self.assertEqual(row["tva_deductible"], 22471.865)
		self.assertIsNone(row["ded_base"])  # the DM's F5_2_4 brut is FIXE
		self.assertEqual(row["gross"], 13654.9)
		self.assertEqual(row["irpp"], 2126.599)
		self.assertEqual(row["css"], 57.639)
		self.assertEqual(row["tfp"], 273.098)
		self.assertEqual(row["foprolos"], 136.549)
		self.assertEqual(row["rs1"], 1606.484)
		self.assertEqual(row["rs3"], 35.7)
		self.assertEqual(row["loyer"], 3266.887)
		self.assertEqual(row["rs_loyer"], 326.688)
		self.assertEqual(row["timbre"], 370.0)
		self.assertEqual(row["tva_a_payer"], 2284.075)
		self.assertEqual(row["credit_suivant"], 0.0)
		self.assertEqual(row["total"], 7528.313)
		# CNSS / S.IMPOS exist only on the declared side
		self.assertIsNone(row["cnss"])
		self.assertIsNone(row["s_impos"])

	def test_declared_row_maps_the_lignes_and_derives(self):
		row = row_from_mensuelle(1, mensuelle_lignes())
		self.assertEqual(row["ht7"], 1092.76)
		self.assertEqual(row["tva7"], 76.4932)
		self.assertEqual(row["ded_base"], 119602.155)
		self.assertEqual(row["s_impos"], 12578.236)
		# CNSS = S.BRUT - S.IMPOS
		self.assertEqual(row["cnss"], round(13654.922 - 12578.236, 3))
		# the declared TVA position: collected - deductible (positive -> P)
		self.assertEqual(row["tva_a_payer"], 2284.075)
		self.assertIsNone(row["credit_suivant"])
		self.assertEqual(row["total"], 7528.313452)

	def test_declared_credit_month_goes_to_the_r_column(self):
		# July: collected 28993.29645 - deductible 30013.055 = -1019.75855
		lignes = [
			{"code_rubrique": "F5_1_1", "base_declaree": 2885.671429, "montant_declare": 201.997},
			{"code_rubrique": "F5_1_3", "base_declaree": 151533.155, "montant_declare": 28791.29945},
			{"code_rubrique": "F5_2_4", "base_declaree": 157963.4474, "montant_declare": 30013.055},
			{"code_rubrique": "TOTAL", "base_declaree": None, "montant_declare": 6808.899076},
		]
		row = row_from_mensuelle(7, lignes)
		self.assertIsNone(row["tva_a_payer"])
		self.assertEqual(row["credit_suivant"], 1019.759)


# The January portal receipt (the addendum's Liquidé figures).
PORTAL_JANUARY = {
	"lines": [
		{"impot": "Retenue a la Source", "total": 4153.109},
		{"impot": "TFP", "total": 273.098},
		{"impot": "FOPROLOS", "total": 136.549},
		{"impot": "TVA", "total": 2284.074},
		{"impot": "Droit de timbre", "total": 370.0},
		{"impot": "TCL", "total": 311.481},
		{"impot": "Reliquat minimum de perception", "total": 0.0},
	],
	"montant_liquide": 7528.311,
}


class TestLiquideRows(unittest.TestCase):
	def test_liquide_row_fills_the_receipt_columns(self):
		row = row_from_liquide(1, PORTAL_JANUARY)
		self.assertEqual(row["tva_a_payer"], 2284.074)
		self.assertEqual(row["timbre"], 370.0)
		self.assertEqual(row["tcl"], 311.481)
		self.assertEqual(row["total"], 7528.311)
		# the portal recomputes lump sums: no HT/RS breakdown on this side
		self.assertIsNone(row["ht7"])
		self.assertIsNone(row["irpp"])

	def test_missing_portal_is_blank(self):
		row = row_from_liquide(1, None)
		self.assertEqual(row["mois"], "01")
		self.assertIsNone(row["total"])


class TestEcartRow(unittest.TestCase):
	def test_ecart_is_declared_minus_calculated(self):
		calcule = row_from_declaration(1, dm_payload())
		declare = row_from_mensuelle(1, mensuelle_lignes())
		row = ecart_row(1, declare, calcule)
		# 76.4932 - 76.493 = 0.0002: below the millime precision, the cell reads 0.000
		self.assertEqual(row["tva7"], 0.0)
		self.assertEqual(row["gross"], 0.022)  # the declared gross vs the ledger
		self.assertNotIn("tcl", row["out_of_tolerance"])

	def test_out_of_tolerance_columns_are_named(self):
		calcule = row_from_declaration(1, dm_payload())
		declare = row_from_mensuelle(1, mensuelle_lignes())
		declare["tva_deductible"] = declare["tva_deductible"] + 5.0  # a real ecart
		row = ecart_row(1, declare, calcule)
		self.assertIn("tva_deductible", row["out_of_tolerance"])
		self.assertNotIn("tva7", row["out_of_tolerance"])

	def test_missing_side_stays_blank(self):
		calcule = row_from_declaration(1, dm_payload())
		declare = row_from_mensuelle(1, None)
		row = ecart_row(1, declare, calcule)
		self.assertIsNone(row["ht7"])
		self.assertEqual(row["out_of_tolerance"], [])

	def test_tolerance_is_the_millime_fudge(self):
		self.assertEqual(ECART_TOLERANCE, 0.005)


class TestRecap(unittest.TestCase):
	def test_twelve_months_with_missing_months_blank(self):
		recap = build_recap({1: dm_payload()}, {1: mensuelle_lignes()})
		self.assertEqual(recap["months"], list(range(1, 13)))
		self.assertEqual(len(recap["rows"]["calcule"]), 12)
		# January carries figures, February is blank
		self.assertEqual(recap["rows"]["calcule"][0]["total"], 7528.313)
		for key, value in recap["rows"]["calcule"][1].items():
			if key != "mois":
				self.assertIsNone(value)
		self.assertEqual(recap["rows"]["declare"][1]["mois"], "02")
		self.assertIsNone(recap["rows"]["declare"][1]["total"])

	def test_totals_row_sums_present_months(self):
		calcule_rows = {1: dm_payload()}
		# a second month, half the January figures
		import copy

		february = copy.deepcopy(dm_payload())
		for line in february["lines"]:
			line["montant_brut"] = round(line["montant_brut"] / 2, 3)
			line["retenu"] = round(line["retenu"] / 2, 3)
		february["total_a_payer"] = round(february["total_a_payer"] / 2, 3)
		calcule_rows[2] = february
		recap = build_recap(calcule_rows, {})
		totals = recap["totals"]["calcule"]
		self.assertEqual(totals["mois"], "TOTAL")
		self.assertEqual(totals["total"], round(7528.313 + 3764.157, 3))
		self.assertEqual(totals["irpp"], round(2126.599 + 1063.3, 3))
		# CNSS/S.IMPOS stay blank in the totals when no month carries them
		self.assertIsNone(totals["cnss"])

	def test_ecart_months_and_dashboard(self):
		recap = build_recap({1: dm_payload()}, {1: mensuelle_lignes()})
		# January: only the gross drifts beyond the tolerance (0.022)
		self.assertEqual(recap["ecart_months"], [1])
		dashboard = dashboard_aggregates(recap, {1: "Depose", 2: "Cloture"})
		self.assertEqual(dashboard["months_depose"], 1)
		self.assertEqual(dashboard["months_cloture"], 1)
		self.assertEqual(dashboard["months_a_faire"], 10)
		self.assertEqual(dashboard["months_with_ecarts_count"], 1)
		self.assertEqual(dashboard["total_a_payer_cumule"], 7528.313)
		# RS cumulés = IRPP + CSS + RS 1% + RS 3% + RS loyers (the Calculé side)
		self.assertEqual(
			dashboard["rs_cumules"],
			round(2126.599 + 57.639 + 1606.484 + 35.7 + 326.688, 3),
		)

	def test_liquide_rows_and_ecart_pairs(self):
		recap = build_recap({1: dm_payload()}, {1: mensuelle_lignes()}, {1: PORTAL_JANUARY})
		self.assertEqual(recap["rows"]["liquide"][0]["total"], 7528.311)
		self.assertIsNone(recap["rows"]["liquide"][1]["total"])
		# the écart table: three comparison pairs, the portal pairs only for
		# the months that carry a receipt
		pairs = recap["rows"]["ecarts"]
		pair_labels = [row["mois"].split(" · ")[1] for row in pairs if row["mois"].startswith("0")]
		self.assertIn("Déclaré vs Calculé", pair_labels)
		self.assertIn("Déclaré vs Liquidé", pair_labels)
		self.assertIn("Calculé vs Liquidé", pair_labels)
		# January's portal variances: all inside the tolerances
		january_liquide = [
			row for row in pairs if row["mois"].startswith("01") and "Liquidé" in row["mois"]
		]
		for row in january_liquide:
			self.assertEqual(row["out_of_tolerance"], [])
		# the totals rows carry the pair tags
		self.assertIn("TOTAL · Déclaré vs Liquidé", [row["mois"] for row in pairs])

	def test_liquide_variance_feeds_ecart_months(self):
		# a portal TVA far off the calculated one flags the month
		portal = {
			"lines": [{"impot": "TVA", "total": 2500.0}],
			"montant_liquide": 7500.0,
		}
		recap = build_recap({1: dm_payload()}, {1: mensuelle_lignes()}, {1: portal})
		self.assertIn(1, recap["ecart_months"])

	def test_columns_in_axeane_order(self):
		recap = build_recap({}, {})
		labels = [column["label"] for column in recap["columns"]]
		self.assertEqual(
			labels[:13],
			["MOIS", "HT7", "TVA7", "HT19", "TVA19", "VT en susp", "TTC", "TCL", "AC",
			 "TVA AC", "DT", "P", "R"],
		)
		self.assertEqual(
			labels[13:],
			["S.BRUT", "CNSS", "S.IMPOS", "IRPP", "CSS", "TFP", "FOPROLOS", "RS 1%",
			 "RS 3%", "Loyer", "RS Loyer", "TOTAL"],
		)


if __name__ == "__main__":
	unittest.main()
