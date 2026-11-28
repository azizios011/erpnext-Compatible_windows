# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for the SCE mapping (sce_mapping.py): the Bilan
rubriques (prefix ownership, longest-prefix wins, 28x/29x netting, sign
rules), the class 7 - class 6 resultat, the equilibrium verdict and the Etat
de Resultat cascade. Run from the app root:

	python3 erpnext/custom_modules/reports/tests/test_sce_mapping.py -v
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

from erpnext.custom_modules.reports.sce_mapping import (
	build_bilan,
	build_etat,
	classify_balances,
	totals_row,
	variation,
)

# A synthetic year-end balance map: the debit / credit sums per account
# number, exercising every rubrique of the mapping.
BALANCES_N = {
	"211000": {"debit": 50000.0, "credit": 0.0},          # immo incorporelles brut
	"281100": {"debit": 0.0, "credit": 20000.0},          # amort. incorporelles
	"230000": {"debit": 120000.0, "credit": 0.0},         # constructions brut
	"283000": {"debit": 0.0, "credit": 30000.0},          # amort. constructions
	"270000": {"debit": 25000.0, "credit": 0.0},          # immo financieres
	"310000": {"debit": 18000.0, "credit": 0.0},          # stocks brut
	"390000": {"debit": 0.0, "credit": 2000.0},           # provision stocks
	"411000": {"debit": 96000.0, "credit": 0.0},          # clients
	"411100": {"debit": 0.0, "credit": 1500.0},           # client credit note
	"436600": {"debit": 6200.0, "credit": 0.0},           # TVA deductible
	"436666": {"debit": 0.0, "credit": 900.0},            # retenue TVA (liability!)
	"500000": {"debit": 12000.0, "credit": 0.0},          # placements
	"531000": {"debit": 15400.0, "credit": 0.0},          # banque
	"101000": {"debit": 0.0, "credit": 100000.0},         # capital
	"111000": {"debit": 0.0, "credit": 25000.0},          # reserves
	"120000": {"debit": 0.0, "credit": 15000.0},          # report a nouveau
	"160000": {"debit": 0.0, "credit": 48000.0},          # emprunts
	"150000": {"debit": 0.0, "credit": 9000.0},           # provisions (long terme)
	"401000": {"debit": 0.0, "credit": 72000.0},          # fournisseurs
	"432100": {"debit": 0.0, "credit": 2126.599},         # RAS salaires
	"436719": {"debit": 0.0, "credit": 24679.447},        # TVA collectee
	"436707": {"debit": 0.0, "credit": 76.4932},          # TVA collectee 7%
	"436520": {"debit": 0.0, "credit": 311.481},          # TCL due
	"437000": {"debit": 0.0, "credit": 370.0},            # timbre due
	"607000": {"debit": 148188.34, "credit": 0.0},        # achats marchandises
	"603700": {"debit": 0.0, "credit": 4500.0},           # variation de stock (credit)
	"622000": {"debit": 1001.0, "credit": 0.0},           # honoraires
	"613000": {"debit": 3266.886, "credit": 0.0},         # loyers
	"640000": {"debit": 10000.0, "credit": 0.0},          # salaires
	"641000": {"debit": 3654.9, "credit": 0.0},
	"681000": {"debit": 12400.0, "credit": 0.0},          # dotations
	"670000": {"debit": 326.0, "credit": 0.0},            # charges financieres
	"690000": {"debit": 800.0, "credit": 0.0},            # impot sur benefice
	"707000": {"debit": 0.0, "credit": 195606.5, },       # ventes TTC
	"706000": {"debit": 0.0, "credit": 500.0},            # autres revenus
	"720000": {"debit": 2200.0, "credit": 0.0},           # production immobilisee (DEBIT!)
	"771000": {"debit": 0.0, "credit": 90.0},             # produits de placements
	"479000": {"debit": 123.0, "credit": 0.0},          # autres actifs courants
	# a zero-balance account: never reported anywhere
	"590000": {"debit": 0.0, "credit": 0.0},
}

# Balance the synthetic ledger: every journal entry is balanced, so the
# whole ledger must be — the plug lands on the long-term borrowing. Without
# it the bilan reads "Non equilibre" over a bookkeeping artifact.
_balance_plug = round(
	sum(v["debit"] for v in BALANCES_N.values()) - sum(v["credit"] for v in BALANCES_N.values()), 3
)
if _balance_plug > 0:
	BALANCES_N["169000"] = {"debit": 0.0, "credit": _balance_plug}
elif _balance_plug < 0:
	BALANCES_N["169000"] = {"debit": -_balance_plug, "credit": 0.0}

# The previous exercice: a simpler map (some accounts gone, one new).
BALANCES_N1 = {
	"211000": {"debit": 50000.0, "credit": 0.0},
	"281100": {"debit": 0.0, "credit": 15000.0},
	"230000": {"debit": 120000.0, "credit": 0.0},
	"283000": {"debit": 0.0, "credit": 22000.0},
	"310000": {"debit": 15000.0, "credit": 0.0},
	"411000": {"debit": 88000.0, "credit": 0.0},
	"531000": {"debit": 9000.0, "credit": 0.0},
	"101000": {"debit": 0.0, "credit": 100000.0},
	"111000": {"debit": 0.0, "credit": 20000.0},
	"120000": {"debit": 0.0, "credit": 5000.0},
	"160000": {"debit": 0.0, "credit": 55000.0},
	"401000": {"debit": 0.0, "credit": 63000.0},
	"607000": {"debit": 130000.0, "credit": 0.0},
	"707000": {"debit": 0.0, "credit": 170000.0},
}


from erpnext.custom_modules.reports.sce_mapping import BILAN_RUBRIQUES  # noqa: E402


def _values_by_key(balances):
	return classify_balances(balances, BILAN_RUBRIQUES)


class TestClassification(unittest.TestCase):
	def test_longest_prefix_wins_on_the_436_collision(self):
		# 4366 (asset) vs the exact 436666 (liability): the longest wins
		values, _unmapped = classify_balances(
			{"436600": {"debit": 100.0, "credit": 0.0},
			 "436666": {"debit": 0.0, "credit": 90.0}},
			BILAN_RUBRIQUES,
		)
		self.assertEqual(values.get("actifs_courants_autres"), 100.0)
		self.assertEqual(values.get("passifs_courants_autres"), 90.0)

	def test_amortissements_net_against_their_asset(self):
		values, _ = _values_by_key(
			{"211000": {"debit": 50000.0, "credit": 0.0},
			 "281100": {"debit": 0.0, "credit": 20000.0}}
		)
		self.assertEqual(values["immob_incorporelles"], 30000.0)

	def test_provision_nets_the_stock(self):
		values, _ = _values_by_key(
			{"310000": {"debit": 18000.0, "credit": 0.0},
			 "390000": {"debit": 0.0, "credit": 2000.0}}
		)
		self.assertEqual(values["stocks"], 16000.0)

	def test_unmapped_balances_are_listed_and_zero_balances_dropped(self):
		values, unmapped = classify_balances(
			{"999999": {"debit": 123.0, "credit": 0.0},
			 "590000": {"debit": 0.0, "credit": 0.0}},
			BILAN_RUBRIQUES,
		)
		self.assertEqual(values, {})
		self.assertEqual(len(unmapped), 1)
		self.assertEqual(unmapped[0]["number"], "999999")
		self.assertEqual(unmapped[0]["net"], 123.0)


class TestBilan(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.bilan = build_bilan(BALANCES_N, BALANCES_N1)
		cls.etat_net_expected = build_etat(BALANCES_N, BALANCES_N1)["resultat_net"]

	def _rubrique(self, key):
		return next(row for row in self.bilan["rows"] if row.get("key") == key)

	def test_rows_have_five_sections_and_a_resultat(self):
		sections = [row["rubrique"] for row in self.bilan["rows"] if row["row_type"] == "section"]
		self.assertEqual(len(sections), 5)
		self.assertEqual(self._rubrique("resultat_exercice")["exercice_n"], 18859.374)

	def test_netting_flows_into_the_rows(self):
		self.assertEqual(self._rubrique("immob_incorporelles")["exercice_n"], 30000.0)
		self.assertEqual(self._rubrique("stocks")["exercice_n"], 16000.0)
		self.assertEqual(self._rubrique("stocks")["exercice_n1"], 15000.0)

	def test_variation_and_percentage(self):
		stocks = self._rubrique("stocks")
		self.assertEqual(stocks["variation"], 1000.0)
		self.assertEqual(stocks["variation_pct"], 6.667)  # 1000 / 15000 * 100

	def test_missing_previous_exercice_blanks_the_column(self):
		bilan = build_bilan(BALANCES_N, None)
		self.assertIsNone(self._rubrique("stocks", bilan["rows"])["exercice_n1"])

	def _rubrique(self, key, rows=None):
		rows = rows if rows is not None else self.bilan["rows"]
		return next(row for row in rows if row.get("key") == key)

	def test_resultat_de_lexercice_is_class7_minus_class6(self):
		# class 7 credit position - class 6 debit position over the mapped
		# rubriques (the financial products, the financial and tax charges
		# included), i.e. the same net result the Etat cascade computes
		produits = 196106.5 - 2200.0 + 90.0
		charges = (148188.34 - 4500.0) + 4267.886 + 13654.9 + 12400.0 + 326.0 + 800.0
		expected = round(produits - charges, 3)
		self.assertEqual(self._rubrique("resultat_exercice")["exercice_n"], expected)
		self.assertEqual(expected, self.etat_net_expected)
		self.assertEqual(self.bilan["unmapped"]["n"], [])

	def test_totals_and_equilibre(self):
		totals = self.bilan["totals"]
		actif_n = totals["exercice_n"]["actif"]
		passif_n = totals["exercice_n"]["passif"]
		# the synthetic ledger balances: actifs == capitaux propres + passifs
		self.assertEqual(actif_n, passif_n)
		self.assertTrue(self.bilan["equilibre"])
		self.assertEqual(self.bilan["difference"], 0.0)

	def test_unbalanced_ledger_is_flagged(self):
		broken = build_bilan(
			{"101000": {"debit": 0.0, "credit": 100000.0},
			 "531000": {"debit": 90000.0, "credit": 0.0}},
			None,
		)
		self.assertFalse(broken["equilibre"])
		self.assertNotEqual(broken["difference"], 0.0)


class TestEtat(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.etat = build_etat(BALANCES_N, BALANCES_N1)

	def _key(self, key):
		return next(row for row in self.etat["rows"] if row.get("key") == key)

	def test_revenus_side(self):
		# 707000 + 706000 credit balances
		self.assertEqual(self._key("revenus")["exercice_n"], 196106.5)

	def test_production_immobilisee_is_debit_natural(self):
		# the 720000 debit balance is a CHARGE-shaped entry for the immobilised
		# production: the rubrique is credit-natural, so a debit reads negative
		self.assertEqual(self._key("production_immobilisee")["exercice_n"], -2200.0)

	def test_cascade(self):
		produits = 196106.5 - 2200.0  # revenus + the negative immobilised line
		charges = (148188.34 - 4500.0) + 4267.886 + 13654.9 + 12400.0
		resultat_exploitation = round(produits - charges, 3)
		self.assertEqual(self._key("resultat_exploitation")["exercice_n"], resultat_exploitation)
		ordinary = round(resultat_exploitation - 326.0 + 90.0 - 800.0, 3)
		self.assertEqual(self._key("resultat_ordinaire")["exercice_n"], ordinary)
		self.assertEqual(self._key("resultat_net")["exercice_n"], ordinary)
		self.assertEqual(self.etat["resultat_net"], ordinary)

	def test_benefice_flag(self):
		self.assertTrue(self.etat["benefice"])


class TestVariation(unittest.TestCase):
	def test_variation_blank_when_both_missing(self):
		self.assertEqual(variation(None, None), (None, None))

	def test_variation_without_previous_has_no_percentage(self):
		self.assertEqual(variation(100.0, None), (100.0, None))

	def test_variation_percentage_reads_against_absolute_previous(self):
		self.assertEqual(variation(1500.0, -1000.0)[1], 250.0)
		self.assertEqual(variation(500.0, 1000.0)[1], -50.0)

	def test_totals_row_sums_present_figures(self):
		rows = [{"exercice_n": 10.0, "exercice_n1": None}, {"exercice_n": None, "exercice_n1": 4.0}]
		totals = totals_row(rows)
		self.assertEqual(totals["exercice_n"], 10.0)
		self.assertEqual(totals["exercice_n1"], 4.0)
		self.assertEqual(totals["variation"], 6.0)


if __name__ == "__main__":
	unittest.main()
