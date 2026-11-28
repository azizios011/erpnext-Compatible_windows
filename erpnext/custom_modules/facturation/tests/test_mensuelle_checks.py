# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for the Déclaration Mensuelle checks
(mensuelle_checks.py — the pure core). Run OUTSIDE a site, from the app root:

	python3 erpnext/custom_modules/facturation/tests/test_mensuelle_checks.py -v

The fixtures reproduce the CPR_DM_2026_AOUT_CLEANED workbook's figures (the
cached values of each monthly sheet and its RECAP 2026 rows); the workbook
itself is exercised end-to-end by test_mensuelle_workbook.py.
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

from erpnext.custom_modules.facturation.mensuelle_checks import (
	check_declaration,
	SEVERITY_ERROR,
	SEVERITY_INFO,
	SEVERITY_WARNING,
	STATUS_CONFORME,
	STATUS_ECARTS,
	STATUS_WARNINGS,
	check_recap,
	check_sheet_arithmetic,
	run_checks,
	status_from_controls,
)

# The RECAP 2026 rows (month -> metric), read from the workbook by header.
RECAP = {
	1: {"ht7": 1092.76, "tva7": 76.4932, "ht19": 129891.826, "tva19": 24679.44694, "ttc": 155740.5261, "tcl": 311.4810523, "ded_base": 119602.155, "tva_deductible": 22471.865, "timbre": 370.0, "tva_due": 2284.075},
	2: {"ht7": 1581.99, "tva7": 110.7393, "ht19": 189417.061, "tva19": 35989.24159, "ttc": 227099.0319, "tcl": 454.1980638, "ded_base": 177215.93, "tva_deductible": 33512.929, "timbre": 379.0, "tva_due": 2587.051},
	3: {"ht7": 1085.487, "tva7": 75.98409, "ht19": 126031.651, "tva19": 23946.01369, "ttc": 151139.1358, "tcl": 302.2782716, "ded_base": 116363.685, "tva_deductible": 22067.035, "timbre": 372.0, "tva_due": 1954.964},
	4: {"ht7": 52.483, "tva7": 3.67381, "ht19": 147332.507, "tva19": 27993.17633, "ttc": 175381.8401, "tcl": 350.7636803, "ded_base": 133776.163, "tva_deductible": 25417.471, "timbre": 444.0, "tva_due": 2579.38},
	5: {"ht7": 1176.146, "tva7": 82.33022, "ht19": 168096.504, "tva19": 31938.33576, "ttc": 201293.316, "tcl": 402.586632, "ded_base": 140978.453, "tva_deductible": 26785.906, "timbre": 395.0, "tva_due": 5230.502},
	6: {"ht7": 1441.663, "tva7": 100.91641, "ht19": 154515.394, "tva19": 29357.92486, "ttc": 185415.8983, "tcl": 370.8317965, "ded_base": 125816.889, "tva_deductible": 23905.209, "timbre": 429.0, "tva_due": 5553.631},
	7: {"ht7": 5226.3, "tva7": 365.841, "ht19": 172186.704, "tva19": 32715.47376, "ttc": 210494.3188, "tcl": 420.9886375, "ded_base": 157963.447, "tva_deductible": 30013.055, "timbre": 458.0, "tva_due": 3068.36},
	8: {"ht7": 343.124, "tva7": 24.01868, "ht19": 134318.816, "tva19": 25520.57504, "ttc": 160206.5337, "tcl": 320.4130674, "ded_base": 124564.353, "tva_deductible": 23480.49, "timbre": 337.0, "tva_due": 2064.104},
	9: {"ht7": 971.14, "tva7": 67.9798, "ht19": 215928.802, "tva19": 41026.47238, "ttc": 257994.3942, "tcl": 515.9887884, "ded_base": 201132.7, "tva_deductible": 38155.3, "timbre": 409.0, "tva_due": 2939.152},
	10: {"ht7": 598.633, "tva7": 41.90431, "ht19": 190001.62, "tva19": 36100.3078, "ttc": 226742.4651, "tcl": 453.4849302, "ded_base": 160352.6, "tva_deductible": 30407.09, "timbre": 418.0, "tva_due": 5735.122},
}


def figures(**values):
	"""{figure_key: value} as the extraction produces it."""
	return {key: {"value": value, "cell": None, "formula": None} for key, value in values.items()}


def sheet(month, **values):
	payload = figures(**values)
	payload["sheet"] = f"DM {month:02d}"
	return {"sheet": payload["sheet"], "figures": payload}


def codes(controls):
	return [control["check_code"] for control in controls]


JANUARY = sheet(
	1,
	irpp=2126.599, css=57.639,
	rs_loyer=326.6876, rs_loyer_rate=0.1, rs_loyer_base=3266.886,
	rs3=35.7, rs3_rate=0.03, rs3_base=1190.0,
	rs1=1606.484, rs1_rate=0.01, rs1_base=160648.4, rs_total=4153.1096,
	tfp=273.09844, tfp_rate=0.02, gross=13654.922, foprolos=136.54922, foprolos_rate=0.01,
	ht7=1092.76, tva7=76.4932, tva7_rate=0.07,
	ht19=129891.826, tva19=24679.44694, tva19_rate=0.19,
	ded_autres=22471.865, ded_base=119602.155,
	tva_collectee=24755.94014, tva_deductible=22471.865, carry_prev=0.0, tva_due=2284.07514,
	timbre=370.0, timbre_count=370.0,
	tcl=311.4810523, tcl_rate=0.002, ttc=155740.5261,
	total=7528.313452,
)

# DM 05: a stale copy of DM 04 — internally consistent, but nothing matches
# the RECAP any more (timbre 444 = April's, HT19/deductible/timbre wrong).
DM05 = sheet(
	5,
	irpp=2688.946, css=66.415,
	rs_loyer=0.0, rs_loyer_rate=0.1, rs_loyer_base=0.0,
	rs3=0.0, rs3_rate=0.03, rs3_base=0.0,
	rs1=1437.946, rs1_rate=0.01, rs1_base=143794.6, rs_total=4193.307,
	tfp=0.0, tfp_rate=0.02, gross=0.0, foprolos=0.0, foprolos_rate=0.01,
	ht7=1176.146, tva7=82.33122, tva7_rate=0.07,
	ht19=154536.79, tva19=29361.9901, tva19_rate=0.19,
	ded_autres=0.0, ded_base=0.0,
	tva_collectee=29444.32132, tva_deductible=0.0, carry_prev=0.0, tva_due=29444.32132,
	timbre=444.0, timbre_count=444.0,
	tcl=370.3145146, tcl_rate=0.002, ttc=185157.2573,
	total=34451.94283,
)

# DM 07 (recent layout): the grand total omits the TVA line, and its sales
# are lower than the RECAP's.
DM07 = sheet(
	7,
	irpp=2737.828, css=67.155,
	rs_loyer=653.377, rs_loyer_rate=0.1, rs_loyer_base=6533.77,
	rs1=2056.84, rs1_rate=0.01, rs1_base=205684.0, rs_total=5515.2,
	tfp=312.58322, tfp_rate=0.02, gross=15629.161, foprolos=156.29161, foprolos_rate=0.01,
	ht7=2885.671429, tva7=201.997, tva7_rate=0.07,
	ht19=151533.155, tva19=28791.29945, tva19_rate=0.19,
	ded_autres=30013.055, ded_base=157963.4474,
	tva_collectee=28993.29645, tva_deductible=30013.055, carry_prev=0.0, tva_due=1019.75855,
	timbre=458.0, timbre_count=458.0,
	tcl=366.8242458, tcl_rate=0.002, ttc=183412.1229,
	total=6808.899076,
)

# DM 09: everything agrees with the RECAP except the timbre (410 vs 409).
DM09 = sheet(
	9,
	irpp=2601.273, css=65.094,
	rs_loyer=0.0, rs_loyer_rate=0.1, rs_loyer_base=0.0,
	rs3=46.392, rs3_rate=0.03, rs3_base=1546.4,
	rs1=2684.159, rs1_rate=0.01, rs1_base=268415.9, rs_total=5396.918,
	tfp=303.45448, tfp_rate=0.02, gross=15172.724, foprolos=151.72724, foprolos_rate=0.01,
	ht7=971.14, tva7=67.9798, tva7_rate=0.07,
	ht19=215928.802, tva19=41026.47238, tva19_rate=0.19,
	ded_autres=38155.3, ded_base=201132.7,
	tva_collectee=41094.45218, tva_deductible=38155.3, carry_prev=0.0, tva_due=2939.15218,
	timbre=410.0, timbre_count=410.0,
	tcl=515.9887884, tcl_rate=0.002, ttc=257994.3942,
	total=9717.240688,
)

# DM 10: the sheet's deductible TVA is not 19% of its own base, and the
# sheet's carry totals diverge from the RECAP row.
DM10 = sheet(
	10,
	irpp=2677.329, css=66.255,
	rs_loyer=343.023, rs_loyer_rate=0.1, rs_loyer_base=3430.23,
	rs1=2349.998, rs1_rate=0.01, rs1_base=234999.8, rs_total=5436.605,
	tfp=308.59658, tfp_rate=0.02, gross=15429.829, foprolos=154.29829, foprolos_rate=0.01,
	ht7=598.633, tva7=41.90431, tva7_rate=0.07,
	ht19=190001.62, tva19=36100.3078, tva19_rate=0.19,
	ded_autres=32529.616, ded_base=190674.409,
	tva_collectee=36142.21211, tva_deductible=32529.616, carry_prev=0.0, tva_due=3612.59611,
	timbre=418.0, timbre_count=418.0,
	tcl=453.4849302, tcl_rate=0.002, ttc=226742.4651,
	total=10383.58091,
)

CONFORME_MONTHS = {
	1: JANUARY,
	2: sheet(2, irpp=1943.888, css=51.38, rs1=1551.174, rs1_base=155117.4, rs_total=3546.442,
		tfp=242.78468, gross=12139.234, foprolos=121.39234, ht7=1581.99, tva7=110.7403,
		ht19=189417.061, tva19=35989.24159, ded_autres=33512.929, tva_collectee=36099.98189,
		tva_deductible=33512.929, carry_prev=0.0, tva_due=2587.05289, timbre=379.0, timbre_count=379.0,
		tcl=454.1980658, ttc=227099.0329, total=7330.869976),
	3: sheet(3, irpp=2286.775, css=63.763, rs1=1714.709, rs1_base=171470.9, rs_total=4065.247,
		tfp=302.8217, gross=15141.085, foprolos=151.41085, ht7=1085.487, tva7=75.98509,
		ht19=126031.651, tva19=23946.01369, ded_autres=22067.035, ded_base=116363.685,
		tva_collectee=24021.99878, tva_deductible=22067.035, carry_prev=0.0, tva_due=1954.96378,
		timbre=372.0, timbre_count=372.0, tcl=302.2782736, ttc=151139.1368, total=7148.721604),
	4: sheet(4, irpp=2281.338, css=60.428, rs1=1437.946, rs1_base=143794.6, rs_total=3779.712,
		tfp=285.8066, gross=14290.33, foprolos=142.9033, ht7=52.483, tva7=3.67481,
		ht19=147332.507, tva19=27993.17633, ded_autres=25417.471, ded_base=133776.1632,
		tva_collectee=27996.85114, tva_deductible=25417.471, carry_prev=0.0, tva_due=2579.38014,
		timbre=444.0, timbre_count=444.0, tcl=350.7636823, ttc=175381.8411, total=7582.565722),
	6: sheet(6, irpp=2693.119, css=66.478, rs1=1723.153, rs1_base=172315.3, rs_total=4482.75,
		tfp=309.58322, gross=15479.161, foprolos=154.79161, ht7=1441.663, tva7=100.91741,
		ht19=154515.394, tva19=29357.92486, ded_autres=23905.209, ded_base=125816.8895,
		tva_collectee=29458.84227, tva_deductible=23905.209, carry_prev=0.0, tva_due=5553.63327,
		timbre=429.0, timbre_count=429.0, tcl=370.8317985, ttc=185415.8993, total=11300.5899),
	8: sheet(8, irpp=2707.651, css=66.698, rs1=0.0, rs1_base=0.0, rs_total=2774.349,
		tfp=310.55834, gross=15527.917, foprolos=155.27917, ht7=343.124, tva7=24.01868,
		ht19=134318.816, tva19=25520.57504, ded_autres=23480.49, ded_base=124564.353,
		tva_collectee=25544.59372, tva_deductible=23480.49, carry_prev=0.0, tva_due=2064.10372,
		timbre=337.0, timbre_count=337.0, tcl=320.4130674, ttc=160206.5337, total=5961.703297),
}


class TestSheetArithmetic(unittest.TestCase):
	"""A. The sheet against its own numbers."""

	def test_january_arithmetic_passes(self):
		controls = check_sheet_arithmetic(JANUARY)
		self.assertEqual(codes(controls), [])

	def test_millime_fudges_stay_within_tolerance(self):
		# DM 06's TVA7 formula carries a +0.001 fudge; DM 01's RS loyer -0.001
		june = sheet(6, ht7=1441.663, tva7=100.91741, tva7_rate=0.07)
		self.assertEqual(codes(check_sheet_arithmetic(june)), [])
		rent = sheet(1, rs_loyer=326.6876, rs_loyer_rate=0.1, rs_loyer_base=3266.886)
		self.assertEqual(codes(check_sheet_arithmetic(rent)), [])

	def test_broken_rate_is_flagged(self):
		broken = sheet(1, ht7=1092.76, tva7=90.0, tva7_rate=0.07)
		controls = check_sheet_arithmetic(broken)
		self.assertIn("TVA7_CALC", codes(controls))

	def test_grand_total_must_sum_all_parts(self):
		# DM 07: the sheet's total omits the TVA line (6808.90); the parts sum
		# to 5789.14 once the (negative) TVA due is included
		controls = check_sheet_arithmetic(DM07)
		total = next(c for c in controls if c["check_code"] == "TOTAL_CALC")
		self.assertEqual(total["declare"], 6808.899076)
		self.assertEqual(total["attendu"], 5789.14)
		self.assertEqual(total["ecart"], 1019.759)
		self.assertEqual(total["severity"], SEVERITY_ERROR)

	def test_consistent_sheet_total_passes(self):
		self.assertEqual(codes(check_sheet_arithmetic(DM05)), [])
		self.assertEqual(codes(check_sheet_arithmetic(DM09)), [])
		self.assertEqual(codes(check_sheet_arithmetic(DM10)), [])


class TestRecapComparison(unittest.TestCase):
	"""B. The sheet against the RECAP row of the same month."""

	def test_months_1_2_3_4_6_8_are_conforme_against_recap(self):
		for month, doc in CONFORME_MONTHS.items():
			controls = check_recap(doc, RECAP[month])
			self.assertEqual(
				codes(controls),
				[],
				msg=f"mois {month:02d}: ecarts inattendus {codes(controls)}",
			)

	def test_dm05_stale_copy_is_flagged(self):
		controls = check_recap(DM05, RECAP[5])
		self.assertIn("RECAP_HT19", codes(controls))
		self.assertIn("RECAP_TIMBRE", codes(controls))
		timbre = next(c for c in controls if c["check_code"] == "RECAP_TIMBRE")
		self.assertEqual((timbre["declare"], timbre["attendu"]), (444.0, 395.0))
		self.assertEqual(status_from_controls(controls), STATUS_ECARTS)

	def test_dm07_sales_lower_than_recap(self):
		controls = check_recap(DM07, RECAP[7])
		self.assertIn("RECAP_HT7", codes(controls))
		self.assertIn("RECAP_TVA_DUE", codes(controls))
		self.assertEqual(status_from_controls(controls), STATUS_ECARTS)

	def test_dm09_timbre_only(self):
		controls = check_recap(DM09, RECAP[9])
		self.assertEqual(codes(controls), ["RECAP_TIMBRE"])
		self.assertEqual(
			(next(c for c in controls if c["check_code"] == "RECAP_TIMBRE")["declare"], 409.0)[0],
			410.0,
		)
		self.assertEqual(status_from_controls(controls), STATUS_ECARTS)

	def test_dm10_tva_and_totals_flagged(self):
		controls = check_recap(DM10, RECAP[10])
		self.assertIn("RECAP_TVA_DUE", codes(controls))
		self.assertIn("RECAP_DED_BASE", codes(controls))
		self.assertIn("RECAP_TVA_DEDUCTIBLE", codes(controls))
		self.assertEqual(status_from_controls(controls), STATUS_ECARTS)

	def test_missing_recap_row_is_info(self):
		controls = check_recap(JANUARY, None)
		self.assertEqual(codes(controls), ["RECAP_ABSENTE"])
		self.assertEqual(controls[0]["severity"], SEVERITY_INFO)


class TestDeclarationComparison(unittest.TestCase):
	"""C. The declared figures against the ledger-computed DM."""

	@classmethod
	def setUpClass(cls):
		# the January Declaration Transaction from prompt 1 (the ledger
		# computation): the typed gross differs by 0.022 — a genuine ecart
		cls.dm = {
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
		cls.sheet_with_rubriques = {
			**JANUARY,
			"rubriques": [
				{"code": "F1_1", "base": 13654.922, "montant": 2126.599},
				{"code": "F1_3", "base": None, "montant": 57.639},
				{"code": "F1_4_1", "base": 3266.886, "montant": 326.6876},
				{"code": "F1_6", "base": 1190.0, "montant": 35.7},
				{"code": "F1_17_1", "base": 160648.4, "montant": 1606.484},
				{"code": "F2_1", "base": 13654.922, "montant": 273.09844},
				{"code": "F3_1", "base": 13654.922, "montant": 136.54922},
				{"code": "F5_1_1", "base": 1092.76, "montant": 76.4932},
				{"code": "F5_1_3", "base": 129891.826, "montant": 24679.44694},
				{"code": "F5_2_4", "base": 119602.155, "montant": 22471.865},
				{"code": "F7", "base": 370.0, "montant": 370.0},
				{"code": "F9_3_1", "base": 155740.5261, "montant": 311.4810523},
				{"code": "TOTAL", "base": None, "montant": 7528.313452},
			],
		}

	def test_absent_dm_is_info(self):
		controls = check_declaration(JANUARY, None)
		self.assertEqual(codes(controls), ["DM_ABSENTE"])
		self.assertEqual(controls[0]["severity"], SEVERITY_INFO)

	def test_gross_drift_is_flagged(self):
		# the declared gross (13654.922) vs the ledger salaries (13654.9)
		controls = check_declaration(self.sheet_with_rubriques, self.dm)
		base = next(c for c in controls if c["check_code"] == "DM_F1_1_BASE")
		self.assertEqual(base["ecart"], 0.022)
		self.assertEqual(base["severity"], SEVERITY_ERROR)

	def test_matched_figures_do_not_flag(self):
		controls = check_declaration(self.sheet_with_rubriques, self.dm)
		self.assertNotIn("DM_F1_1_MONTANT", codes(controls))
		self.assertNotIn("DM_F5_1_1_BASE", codes(controls))
		self.assertNotIn("DM_TOTAL", codes(controls))
		self.assertNotIn("DM_TVA_DUE", codes(controls))

	def test_total_drift_is_flagged(self):
		dm = {**self.dm, "total_a_payer": 7520.0}
		controls = check_declaration(self.sheet_with_rubriques, dm)
		total = next(c for c in controls if c["check_code"] == "DM_TOTAL")
		self.assertEqual(total["ecart"], 8.313)


class TestStatusRules(unittest.TestCase):
	def test_info_only_stays_conforme(self):
		self.assertEqual(
			status_from_controls([{"severity": SEVERITY_INFO}]), STATUS_CONFORME
		)

	def test_warning_gives_avertissements(self):
		self.assertEqual(
			status_from_controls([{"severity": SEVERITY_WARNING}]), STATUS_WARNINGS
		)

	def test_error_gives_ecarts(self):
		self.assertEqual(
			status_from_controls(
				[{"severity": SEVERITY_INFO}, {"severity": SEVERITY_ERROR}]
			),
			STATUS_ECARTS,
		)

	def test_empty_controls_are_conforme(self):
		self.assertEqual(status_from_controls([]), STATUS_CONFORME)


class TestRunChecks(unittest.TestCase):
	def test_full_run_on_january(self):
		result = run_checks(JANUARY, RECAP[1], None)
		self.assertEqual(codes(result["controls"]), ["DM_ABSENTE"])
		self.assertEqual(result["status"], STATUS_CONFORME)

	def test_full_run_on_dm07(self):
		result = run_checks(DM07, RECAP[7], None)
		self.assertIn("TOTAL_CALC", codes(result["controls"]))
		self.assertEqual(result["status"], STATUS_ECARTS)


if __name__ == "__main__":
	unittest.main()
