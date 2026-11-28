# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for the Déclaration Mensuelle engine
(declaration_engine.py — the pure core plus the shared account-interval
matcher). Run OUTSIDE a site, from the app root:

	python3 erpnext/custom_modules/entries/tests/test_declaration_engine.py -v

The scenarios reproduce the CPR comparative grid (January totals and the
VAT carry chain between February and March 2026) with fixture balances that
are self-consistent by construction.
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
		# the whitelisted workflow methods decorate at import time; the stub
		# passes the functions through untouched
		_frappe.whitelist = lambda **kwargs: (lambda fn: fn)
		_utils = types.ModuleType("frappe.utils")
		_utils.cstr = lambda value: str(value) if value is not None else ""
		_utils.cint = lambda value: int(value or 0) if str(value).lstrip("-").isdigit() or isinstance(value, (int, float)) else 0
		_utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision else float(value or 0)
		_frappe.utils = _utils
		sys.modules["frappe"] = _frappe
		sys.modules["frappe.utils"] = _utils
else:
	if not hasattr(sys.modules["frappe"], "_"):
		sys.modules["frappe"]._ = lambda value, *a, **kw: value

_repo_root = str(pathlib.Path(__file__).resolve().parents[4])
if _repo_root not in sys.path:
	sys.path.insert(0, _repo_root)

from erpnext.custom_modules.entries.declaration_engine import (
	TCL_THEORETICAL_CODE,
	assert_calendar_aligned,
	build_avertissements,
	compute_declaration_core,
	compute_rubriques,
	compute_totals,
	month_bounds,
	rate3,
	render_rubriques_html,
	retenu_of,
	uncovered_watch_accounts,
)
from erpnext.custom_modules.organization.account_interval import (
	match_interval,
	match_intervals,
)


def row(name, debit=0.0, credit=0.0):
	return {"debit": debit, "credit": credit, "rows": [name]}


def standard_config():
	"""The seed's standard rubrique config, as the engine's pure core reads
	it: compte intervals as (number, upper) tuples (empty upper = prefix)."""
	familles = {1: "Retenue_A_La_Source", 2: "TFP", 3: "FOPROLOS", 5: "TVA", 7: "Droit_de_timbre", 9: "TCL"}

	def rubrique(code, famille, libelle, taux, brut_type, brut_sens, brut, retenu_type, retenu_sens, retenu):
		return {
			"code": code,
			"famille": familles[famille],
			"famille_order": famille,
			"libelle": libelle,
			"taux": taux,
			"type_calcul_brut": brut_type,
			"sens_brut": brut_sens,
			"comptes_brut": brut,
			"type_calcul_retenu": retenu_type,
			"sens_retenu": retenu_sens,
			"comptes_retenu": retenu,
		}

	salaires_brut = [("640000", ""), ("641000", ""), ("641010", "")]
	return [
		rubrique("F1_1", 1, "RS Salaires", 0, "COMPTE", "DEBIT", salaires_brut, "COMPTE", "CREDIT", [("432100", ""), ("432101", "")]),
		rubrique("F1_3", 1, "CSS", 1, "FIXE", "", [], "COMPTE", "CREDIT", [("432102", ""), ("432110", ""), ("432111", "")]),
		rubrique("F1_4_1", 1, "RS Loyers", 10, "COMPTE", "DEBIT", [("613000", "")], "COMPTE", "CREDIT", [("432300", "")]),
		rubrique("F1_6", 1, "RS Honoraires", 3, "COMPTE", "DEBIT", [("622000", "")], "COMPTE", "CREDIT", [("432200", "")]),
		rubrique("F1_17_1", 1, "RS Fournisseurs", 1, "COMPTE", "DEBIT", [("607000", "")], "COMPTE", "CREDIT", [("432000", "432081"), ("432122", "")]),
		rubrique("F2_1", 2, "TFP", 2, "COMPTE", "DEBIT", salaires_brut, "BRUT_TAUX", "", []),
		rubrique("F3_1", 3, "FOPROLOS", 1, "COMPTE", "DEBIT", salaires_brut, "BRUT_TAUX", "", []),
		rubrique("F5_1_1", 5, "CA TVA 7%", 7, "RETENU_TAUX", "", [], "COMPTE", "CREDIT", [("436707", "")]),
		rubrique("F5_1_2", 5, "CA TVA 13%", 13, "FIXE", "", [], "FIXE", "", []),
		rubrique("F5_1_3", 5, "CA TVA 19%", 19, "RETENU_TAUX", "", [], "COMPTE", "CREDIT", [("436719", "")]),
		rubrique("F5_2_1", 5, "TVA ded. immobiliers", 0, "FIXE", "", [], "FIXE", "", []),
		rubrique("F5_2_2", 5, "TVA ded. equipements locaux", 0, "FIXE", "", [], "FIXE", "", []),
		rubrique("F5_2_3", 5, "TVA ded. equipements importes", 0, "FIXE", "", [], "FIXE", "", []),
		rubrique("F5_2_4", 5, "TVA ded. autres achats locaux", 0, "FIXE", "", [], "COMPTE", "DEBIT", [("436600", ""), ("436607", ""), ("436613", ""), ("436660", "")]),
		rubrique("F5_2_5", 5, "TVA ded. autres achats importes", 0, "FIXE", "", [], "FIXE", "", []),
		rubrique("F5_3_1", 5, "Retenue TVA 25%", 25, "FIXE", "", [], "COMPTE", "CREDIT", [("436666", "")]),
		rubrique("F7", 7, "Droit de timbre", 1, "FIXE", "", [], "COMPTE", "CREDIT", [("437000", "")]),
		rubrique("F9_3_1", 9, "TCL CA local", 0.2, "COMPTE", "CREDIT", [("707007", ""), ("707019", "")], "COMPTE", "CREDIT", [("436000", ""), ("436520", "")]),
		rubrique("F9_3_2", 9, "TCL CA export", 0.1, "FIXE", "", [], "BRUT_TAUX", "", []),
	]


def january_balances():
	"""January 2026: the ledger aggregates behind the first two scenarios.
	432999 is deliberately uncovered (the watch warning)."""
	return {
		"640000": row("r1", debit=10000.0),
		"641000": row("r2", debit=3654.9),
		"432100": row("r3", credit=2126.599),
		"432102": row("r4", credit=57.639),
		"613000": row("r5", debit=3266.887),
		"432300": row("r6", credit=326.688),
		"622000": row("r7", debit=1190.0),
		"432200": row("r8", credit=35.7),
		"607000": row("r9", debit=160648.4),
		"432000": row("r10", credit=1000.0),
		"432081": row("r11", credit=600.0),
		"432122": row("r12", credit=6.484),
		"436707": row("r13", credit=76.493),
		"436719": row("r14", credit=24679.447),
		"436600": row("r15", debit=22471.865),
		"437000": row("r16", credit=370.0),
		"436000": row("r17", credit=311.481),
		"707007": row("r18", credit=155740.523),
		"432999": row("r19", credit=500.0),
	}


def line_of(lines, code):
	return next(line for line in lines if line["code"] == code)


class TestRounding(unittest.TestCase):
	def test_rate3_rounds_half_up_to_three_decimals(self):
		self.assertEqual(rate3(1092.7571428571428), 1092.757)
		self.assertEqual(rate3(311.481046), 311.481)
		self.assertEqual(rate3(0.0005), 0.001)
		self.assertEqual(rate3(-2092.2375), -2092.238)
		self.assertEqual(rate3(None), 0.0)


class TestCalendar(unittest.TestCase):
	def test_month_bounds(self):
		self.assertEqual(month_bounds(2026, 1), (date(2026, 1, 1), date(2026, 1, 31)))
		self.assertEqual(month_bounds(2024, 2), (date(2024, 2, 1), date(2024, 2, 29)))
		self.assertEqual(month_bounds(2026, 12), (date(2026, 12, 1), date(2026, 12, 31)))
		with self.assertRaises(ValueError):
			month_bounds(2026, 13)

	def test_calendar_alignment_is_enforced(self):
		assert_calendar_aligned(date(2026, 1, 1), date(2026, 12, 31), 2026)
		with self.assertRaises(ValueError):
			assert_calendar_aligned(date(2026, 1, 1), date(2026, 12, 31), 2027)
		with self.assertRaises(ValueError):
			assert_calendar_aligned(date(2026, 3, 15), date(2027, 3, 14), 2026)


class TestIntervalMatching(unittest.TestCase):
	def test_prefix_interval_matches_the_number_and_its_children(self):
		self.assertTrue(match_interval("640000", "640000"))
		self.assertTrue(match_interval("6400001", "640000"))
		self.assertFalse(match_interval("641000", "640000"))

	def test_range_interval_matches_the_boundaries_and_inside(self):
		self.assertTrue(match_interval("432000", "432000", "432081"))
		self.assertTrue(match_interval("432050", "432000", "432081"))
		self.assertTrue(match_interval("432081", "432000", "432081"))
		self.assertFalse(match_interval("432122", "432000", "432081"))

	def test_multi_interval_union(self):
		intervals = [("432000", "432081"), ("432122", "")]
		self.assertTrue(match_intervals("432050", intervals))
		self.assertTrue(match_intervals("432122", intervals))
		self.assertTrue(match_intervals("4321220", intervals))
		self.assertFalse(match_intervals("432200", intervals))


class TestJanuaryDeclaration(unittest.TestCase):
	"""CPR January 2026: the TVA position and the grand total."""

	@classmethod
	def setUpClass(cls):
		cls.result = compute_declaration_core(standard_config(), january_balances(), credit_anterieur=0.0)

	def test_tva_a_payer(self):
		# collectee = 76.493 + 24679.447, deductible = 22471.865
		self.assertEqual(self.result["tva_collectee"], 24755.94)
		self.assertEqual(self.result["tva_deductible"], 22471.865)
		self.assertEqual(self.result["tva_a_payer"], 2284.075)
		self.assertEqual(self.result["credit_suivant"], 0.0)

	def test_retenu_and_theoretical_lines(self):
		lines = self.result["lines"]
		f1_1 = line_of(lines, "F1_1")
		self.assertEqual(f1_1["montant_brut"], 13654.9)
		self.assertEqual(f1_1["retenu"], 2126.599)
		self.assertEqual(f1_1["retenu_theorique"], 0.0)

		f1_4_1 = line_of(lines, "F1_4_1")
		self.assertEqual(f1_4_1["montant_brut"], 3266.887)
		self.assertEqual(f1_4_1["retenu"], 326.688)
		# brut x taux: 3266.887 x 10% = 326.689 — the millime difference the
		# accountant sees as the ecart
		self.assertEqual(f1_4_1["retenu_theorique"], 326.689)
		self.assertEqual(f1_4_1["ecart_theorique"], -0.001)

		f2_1 = line_of(lines, "F2_1")
		self.assertEqual(f2_1["montant_brut"], 13654.9)
		self.assertEqual(f2_1["retenu"], 273.098)

		f5_1_1 = line_of(lines, "F5_1_1")
		# RETENU_TAUX: brut = 76.493 / 7%
		self.assertEqual(f5_1_1["montant_brut"], 1092.757)
		self.assertEqual(f5_1_1["retenu"], 76.493)

	def test_tcl_theoretical_uses_ttc_without_timbre(self):
		# 0.2% x (F5_1_1 brut + retenu + F5_1_3 brut + retenu)
		lines = self.result["lines"]
		self.assertEqual(line_of(lines, TCL_THEORETICAL_CODE)["retenu_theorique"], 311.481)
		# the ledger withheld exactly that: ecart zero
		self.assertEqual(line_of(lines, TCL_THEORETICAL_CODE)["ecart_theorique"], 0.0)
		self.assertEqual(line_of(lines, TCL_THEORETICAL_CODE)["retenu"], 311.481)

	def test_total_a_payer(self):
		# 2126.599 + 57.639 + 326.688 + 35.700 + 1606.484 + 273.098 + 136.549
		# + 2284.075 + 370 + 311.481
		self.assertEqual(self.result["total_rs"], 4153.11)
		self.assertEqual(self.result["total_tfp"], 273.098)
		self.assertEqual(self.result["total_foprolos"], 136.549)
		self.assertEqual(self.result["total_timbre"], 370.0)
		self.assertEqual(self.result["total_tcl"], 311.481)
		self.assertEqual(self.result["total_a_payer"], 7528.313)

	def test_ecritures_collected_for_drill_down(self):
		f1_1 = line_of(self.result["lines"], "F1_1")
		# the two brut rows + the retenu row
		self.assertEqual(f1_1["nb_ecritures"], 3)
		self.assertIn("r1", f1_1["ecritures"])
		self.assertIn("r3", f1_1["ecritures"])

	def test_uncovered_watch_account_warns(self):
		uncovered = uncovered_watch_accounts(january_balances(), standard_config())
		self.assertEqual([u["account_number"] for u in uncovered], ["432999"])
		self.assertEqual(uncovered[0]["movement"], 500.0)
		warnings = build_avertissements(self.result["lines"], uncovered, False)
		self.assertTrue(any("432999" in warning for warning in warnings))

	def test_retenue_tva_warning_when_non_zero(self):
		balances = january_balances()
		balances["436666"] = row("r20", credit=100.0)
		result = compute_declaration_core(standard_config(), balances, credit_anterieur=0.0)
		self.assertEqual(retenu_of(result["lines"], "F5_3_1"), 100.0)
		self.assertTrue(any("Retenue TVA 25%" in warning for warning in result["avertissements"]))

	def test_render_includes_families_and_rows(self):
		html = render_rubriques_html(self.result["lines"], self.result["avertissements"])
		self.assertIn("dm-famille-row", html)
		self.assertIn('data-code="F1_1"', html)
		self.assertIn("2 126.599", html)


class TestTvaCarry(unittest.TestCase):
	"""The sequential credit chain: a credit month feeds the next one."""

	def test_credit_month_carries_forward(self):
		# collectee 27725.084, deductible 29817.322 -> net -2092.238
		balances = {
			"436719": row("c1", credit=27725.084),
			"436600": row("c2", debit=29817.322),
		}
		result = compute_declaration_core(standard_config(), balances, credit_anterieur=0.0)
		self.assertEqual(result["tva_a_payer"], 0.0)
		self.assertEqual(result["credit_suivant"], 2092.238)

	def test_next_month_consumes_the_carry(self):
		# collectee 33382.153, deductible 30392.483, carry -2092.238 (negative = credit)
		balances = {
			"436719": row("d1", credit=33382.153),
			"436600": row("d2", debit=30392.483),
		}
		result = compute_declaration_core(standard_config(), balances, credit_anterieur=-2092.238)
		self.assertEqual(result["tva_a_payer"], 897.432)
		self.assertEqual(result["credit_suivant"], 0.0)

	def test_totals_recompute_from_lines_and_carry(self):
		# the controller's manual-carry path: totals from the FROZEN lines
		january = compute_declaration_core(standard_config(), january_balances(), credit_anterieur=0.0)
		lines = [{"code": line["code"], "retenu": line["retenu"]} for line in january["lines"]]
		totals = compute_totals(lines, -100.0)
		self.assertEqual(totals["tva_a_payer"], 2184.075)
		self.assertEqual(totals["total_a_payer"], 7428.313)
		totals = compute_totals(lines, 50.0)
		self.assertEqual(totals["tva_a_payer"], 2334.075)
		self.assertEqual(totals["credit_suivant"], 0.0)


if __name__ == "__main__":
	unittest.main()
