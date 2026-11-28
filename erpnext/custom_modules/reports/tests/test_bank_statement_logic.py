# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for the rapprochement bancaire core
(bank_statement_logic.py): the cleared-at semantics (marking + date window),
the Bank Reconciliation Statement math (solde comptable, cheques emis /
encaissements non rapproches, solde releve theorique) and the line-view
filters shared with the Rapprochement Manuel page. Run from the app root:

	python3 erpnext/custom_modules/reports/tests/test_bank_statement_logic.py -v
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
		# erpnext/__init__ imports frappe: stub it for the frappe-free core
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

_repo_root = str(pathlib.Path(__file__).resolve().parents[4])
if _repo_root not in sys.path:
	sys.path.insert(0, _repo_root)

from erpnext.custom_modules.bank_reconciliation.bank_statement_logic import (
	compute_statement,
	filter_line_rows,
	is_rapprochee,
	totals,
)

UP_TO = date(2026, 1, 31)


def row(name, posting, debit=0.0, credit=0.0, manuel=0, cleared_on=None, **extra):
	return {
		"name": name,
		"posting_date": date.fromisoformat(posting),
		"debit": debit,
		"credit": credit,
		"rapprochement_manuel": manuel,
		"date_rapprochement": date.fromisoformat(cleared_on) if cleared_on else None,
		"journal": extra.get("journal", "BQ"),
		"account": extra.get("account", "512000 - BANQUE"),
		"tresorerie": extra.get("tresorerie", ""),
		"ref_doc": extra.get("ref_doc", ""),
		"libelle": extra.get("libelle", ""),
	}


class TestClearedAt(unittest.TestCase):
	def test_unmarked_is_never_cleared(self):
		self.assertFalse(is_rapprochee(row("r1", "2026-01-10")))

	def test_marked_without_date_is_not_cleared(self):
		self.assertFalse(is_rapprochee(row("r1", "2026-01-10", manuel=1)))

	def test_marked_and_dated(self):
		self.assertTrue(is_rapprochee(row("r1", "2026-01-10", manuel=1, cleared_on="2026-01-12")))

	def test_marked_with_a_later_date_is_outstanding_at_the_earlier_date(self):
		self.assertFalse(is_rapprochee(row("r1", "2026-01-10", manuel=1, cleared_on="2026-02-05"), as_of=UP_TO))
		self.assertTrue(is_rapprochee(row("r1", "2026-01-10", manuel=1, cleared_on="2026-02-05")))

	def test_cleared_exactly_on_the_date_counts(self):
		self.assertTrue(is_rapprochee(row("r1", "2026-01-10", manuel=1, cleared_on="2026-01-31"), as_of=UP_TO))

	def test_accepts_iso_strings(self):
		self.assertTrue(is_rapprochee(row("r1", "2026-01-10", manuel=1, cleared_on="2026-01-12"), as_of="2026-01-31"))


class TestStatement(unittest.TestCase):
	def test_full_statement_math(self):
		rows = [
			row("a", "2026-01-05", debit=1000.0, manuel=1, cleared_on="2026-01-06"),  # cleared
			row("b", "2026-01-10", credit=120.0),                                # cheque emis outstanding
			row("c", "2026-01-15", debit=300.0),                                 # encaissement outstanding
			row("d", "2026-01-20", debit=50.0, manuel=1, cleared_on="2026-01-22"),  # cleared
			row("e", "2026-02-03", debit=999.0),                                 # after the date: excluded
		]
		statement = compute_statement(rows, UP_TO, solde_initial=500.0)
		self.assertEqual(statement["solde_comptable"], 1000.0 + 300.0 + 50.0 - 120.0)
		self.assertEqual(statement["cheques_emis_non_rapproches"], 120.0)
		self.assertEqual(statement["encaissements_non_rapproches"], 300.0)
		# erpnext's math: balance - total_debit_not_cleared + total_credit_not_cleared
		self.assertEqual(statement["solde_releve_theorique"], 1230.0 - 300.0 + 120.0)
		self.assertEqual(statement["count_rapprochees"], 2)
		self.assertEqual(statement["count_non_rapprochees"], 2)
		self.assertEqual(statement["count_debit_non_rapprochees"], 1)
		self.assertEqual(statement["count_credit_non_rapprochees"], 1)
		self.assertEqual(statement["solde_initial"], 500.0)

	def test_cleared_after_the_date_stays_outstanding(self):
		rows = [
			row("a", "2026-01-10", credit=80.0, manuel=1, cleared_on="2026-02-10"),
		]
		statement = compute_statement(rows, UP_TO)
		self.assertEqual(statement["cheques_emis_non_rapproches"], 80.0)
		self.assertEqual(statement["solde_releve_theorique"], -80.0 + 80.0)

	def test_empty_ledger_reads_zeroes(self):
		statement = compute_statement([], UP_TO)
		self.assertEqual(statement["solde_comptable"], 0.0)
		self.assertEqual(statement["solde_releve_theorique"], 0.0)
		self.assertIsNone(statement["solde_initial"])

	def test_balanced_ledger_theorique_equals_comptable(self):
		rows = [
			row("a", "2026-01-10", debit=500.0, manuel=1, cleared_on="2026-01-11"),
			row("b", "2026-01-12", credit=500.0, manuel=1, cleared_on="2026-01-11"),
		]
		statement = compute_statement(rows, UP_TO)
		self.assertEqual(statement["solde_comptable"], 0.0)
		self.assertEqual(statement["solde_releve_theorique"], 0.0)
		self.assertEqual(statement["count_non_rapprochees"], 0)


class TestLineFilters(unittest.TestCase):
	ROWS = [
		row("a", "2026-01-05", debit=100.0, journal="BQ", tresorerie="CHQ-1", ref_doc="P-1"),
		row("b", "2026-01-10", credit=50.0, manuel=1, cleared_on="2026-01-11", journal="BQ"),
		row("c", "2026-01-20", debit=25.0, journal="CAISSE", account="531000 - CAISSE"),
		row("d", "2026-02-01", credit=10.0, manuel=1, cleared_on="2026-02-03", ref_doc="P-2"),
	]

	def test_type_ecriture_filter(self):
		self.assertEqual([r["name"] for r in filter_line_rows(self.ROWS, {"type_ecriture": "Rapprochees"})], ["b", "d"])
		self.assertEqual(
			[r["name"] for r in filter_line_rows(self.ROWS, {"type_ecriture": "Non rapprochees"})], ["a", "c"]
		)
		self.assertEqual([r["name"] for r in filter_line_rows(self.ROWS, {"type_ecriture": "Toutes"})], ["a", "b", "c", "d"])

	def test_journal_and_account_filters(self):
		self.assertEqual(
			[r["name"] for r in filter_line_rows(self.ROWS, {"journal": "CAISSE"})], ["c"]
		)
		self.assertEqual(
			[r["name"] for r in filter_line_rows(self.ROWS, {"account": "531000 - CAISSE"})], ["c"]
		)

	def test_period_range_is_inclusive(self):
		filtered = filter_line_rows(self.ROWS, {"from_date": "2026-01-10", "to_date": "2026-01-31"})
		self.assertEqual([r["name"] for r in filtered], ["b", "c"])

	def test_tresorerie_and_ref_filters(self):
		self.assertEqual(
			[r["name"] for r in filter_line_rows(self.ROWS, {"tresorerie": "CHQ-1"})], ["a"]
		)
		self.assertEqual(
			[r["name"] for r in filter_line_rows(self.ROWS, {"date_rapprochement": "2026-02-03"})], ["d"]
		)

	def test_oldest_first_ordering(self):
		rows = [
			row("late", "2026-01-20", debit=1.0),
			row("early", "2026-01-02", credit=1.0),
		]
		self.assertEqual([r["name"] for r in filter_line_rows(rows)], ["early", "late"])


class TestTotals(unittest.TestCase):
	def test_totals_and_millimes(self):
		rows = [
			row("a", "2026-01-05", debit=1234.5),
			row("b", "2026-01-06", credit=0.0002),
			row("c", "2026-01-07", credit=1234.0),
		]
		t = totals(rows)
		self.assertEqual(t["total_debit"], 1234.5)
		self.assertEqual(t["total_credit"], 1234.0)  # 0.0002 rounds away at 3 decimals
		self.assertEqual(t["solde"], 0.5)

	def test_empty(self):
		self.assertEqual(totals([]), {"total_debit": 0.0, "total_credit": 0.0, "solde": 0.0})


if __name__ == "__main__":
	unittest.main()
