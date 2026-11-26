# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free unit tests for the imported-entries grouping + classification
(imported_entries_logic.py). Run OUTSIDE a site, from the app root:

	python3 erpnext/custom_modules/reports/tests/test_imported_entries.py -v

(or inside a site with frappe importable, via unittest — the stub below is
skipped entirely when a real frappe is importable: only the erpnext package
chain's module-level `cstr` import needs satisfying otherwise).
"""

import pathlib
import sys
import time
import types
import unittest
from datetime import date

if "frappe" not in sys.modules:
	try:
		import frappe
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

from erpnext.custom_modules.reports.imported_entries_logic import (
	PAYABLE_DOCTYPE,
	RECEIVABLE_DOCTYPE,
	TREASURY_DOCTYPE,
	build_entry_payload,
	classify_group,
	group_imported_rows,
	materialize_plan,
)


def ledger_row(
	name,
	journal,
	mvt,
	account,
	debit=0.0,
	credit=0.0,
	libelle="",
	ref_doc="",
	tresorerie="",
	posting_date=None,
):
	return {
		"name": name,
		"journal": journal,
		"mvt": mvt,
		"account": account,
		"debit": debit,
		"credit": credit,
		"libelle": libelle,
		"ref_doc": ref_doc,
		"tresorerie": tresorerie,
		"import_batch": "GL-TEST",
		"entreprise": "ENT-1",
		"exercice": "EX-2026",
		"posting_date": posting_date or date(2026, 3, 15),
	}


ACCOUNT_NUMBERS = {
	"401000": "401000",  # Fournisseurs
	"411000": "411000",  # Clients
	"601000": "601000",  # Achats
	"701000": "701000",  # Ventes
	"532000": "532000",  # Banque
	"445600": "445600",  # TVA deductible
	"101000": "101000",  # Capital
	"112000": "112000",  # Report a nouveau
}


def plan_of(rows, journal_types):
	return materialize_plan(rows, journal_types, ACCOUNT_NUMBERS)


class TestGroupImportedRows(unittest.TestCase):
	def test_rows_of_one_mvt_group_together(self):
		rows = [
			ledger_row("L1", "AC", "A-1", "601000", debit=100),
			ledger_row("L2", "AC", "A-1", "445600", debit=19),
			ledger_row("L3", "AC", "A-1", "401000", credit=119),
		]
		groups = group_imported_rows(rows)
		self.assertEqual(list(groups.keys()), [("AC", "A-1")])
		self.assertEqual(len(groups[("AC", "A-1")]), 3)

	def test_same_mvt_number_in_two_journals_stays_two_groups(self):
		rows = [
			ledger_row("L1", "AC", "X-1", "601000", debit=50),
			ledger_row("L2", "AC", "X-1", "401000", credit=50),
			ledger_row("L3", "VT", "X-1", "411000", debit=70),
			ledger_row("L4", "VT", "X-1", "701000", credit=70),
		]
		groups = group_imported_rows(rows)
		self.assertEqual(sorted(groups.keys()), [("AC", "X-1"), ("VT", "X-1")])

	def test_grouping_is_journal_and_mvt_only_not_date(self):
		rows = [
			ledger_row("L1", "AC", "A-1", "401000", credit=10, posting_date=date(2026, 1, 5)),
			ledger_row("L2", "AC", "A-1", "532000", debit=10, posting_date=date(2026, 2, 9)),
		]
		groups = group_imported_rows(rows)
		self.assertEqual(len(groups), 1)
		self.assertEqual(len(groups[("AC", "A-1")]), 2)


class TestClassifyGroup(unittest.TestCase):
	def test_supplier_invoice_debits_the_charges(self):
		lines = [
			{"account_number": "601000", "debit": 100, "credit": 0},
			{"account_number": "445600", "debit": 19, "credit": 0},
			{"account_number": "401000", "debit": 0, "credit": 119},
		]
		self.assertEqual(classify_group("Achat", lines), PAYABLE_DOCTYPE)

	def test_supplier_payment_flips_the_sign_but_not_the_doctype(self):
		lines = [
			{"account_number": "401000", "debit": 119, "credit": 0},
			{"account_number": "532000", "debit": 0, "credit": 119},
		]
		self.assertEqual(classify_group("Banque", lines), PAYABLE_DOCTYPE)

	def test_client_invoice_debits_the_client(self):
		lines = [
			{"account_number": "411000", "debit": 120, "credit": 0},
			{"account_number": "701000", "debit": 0, "credit": 120},
		]
		self.assertEqual(classify_group("Vente", lines), RECEIVABLE_DOCTYPE)

	def test_client_payment_flips_the_sign_but_not_the_doctype(self):
		lines = [
			{"account_number": "532000", "debit": 120, "credit": 0},
			{"account_number": "411000", "debit": 0, "credit": 120},
		]
		self.assertEqual(classify_group("Banque", lines), RECEIVABLE_DOCTYPE)

	def test_mixed_group_is_decided_by_a_purchase_journal(self):
		lines = [
			{"account_number": "401000", "debit": 10, "credit": 0},
			{"account_number": "411000", "debit": 0, "credit": 10},
		]
		self.assertEqual(classify_group("Achat", lines), PAYABLE_DOCTYPE)

	def test_mixed_group_is_decided_by_a_sales_journal(self):
		lines = [
			{"account_number": "401000", "debit": 10, "credit": 0},
			{"account_number": "411000", "debit": 0, "credit": 10},
		]
		self.assertEqual(classify_group("Vente", lines), RECEIVABLE_DOCTYPE)

	def test_mixed_group_under_a_neutral_journal_classifies_as_treasury(self):
		lines = [
			{"account_number": "401000", "debit": 10, "credit": 0},
			{"account_number": "411000", "debit": 0, "credit": 10},
		]
		self.assertEqual(classify_group("Banque", lines), TREASURY_DOCTYPE)
		self.assertEqual(classify_group("Operations Diverses", lines), TREASURY_DOCTYPE)

	def test_group_without_auxiliary_lines_classifies_as_treasury(self):
		# opening balances AN / capital / pure bank & tax lines -> Treasury Transaction
		opening = [
			{"account_number": "112000", "debit": 500, "credit": 0},
			{"account_number": "101000", "debit": 0, "credit": 500},
		]
		bank_only = [{"account_number": "532000", "debit": 10, "credit": 10}]
		self.assertEqual(classify_group("Achat", opening), TREASURY_DOCTYPE)
		self.assertEqual(classify_group("Banque", bank_only), TREASURY_DOCTYPE)


class TestMaterializePlan(unittest.TestCase):
	def test_plan_splits_the_doctypes_and_reports_per_journal(self):
		rows = [
			# AC · A-1: supplier invoice → Payable
			ledger_row("L1", "AC", "A-1", "601000", debit=100),
			ledger_row("L2", "AC", "A-1", "401000", credit=100),
			# VT · V-1: client payment → Receivable
			ledger_row("L3", "VT", "V-1", "532000", debit=80),
			ledger_row("L4", "VT", "V-1", "411000", credit=80),
			# BQ · B-1: opening balance without auxiliaries → Treasury
			ledger_row("L5", "BQ", "B-1", "101000", credit=500),
			ledger_row("L6", "BQ", "B-1", "532000", debit=500),
			# same mvt number in two journals: classified independently
			ledger_row("L7", "AC", "X-1", "401000", credit=20),
			ledger_row("L8", "AC", "X-1", "532000", debit=20),
			ledger_row("L9", "VT", "X-1", "411000", debit=30),
			ledger_row("L10", "VT", "X-1", "701000", credit=30),
		]
		journal_types = {"AC": "Achat", "VT": "Vente", "BQ": "Banque"}
		built = plan_of(rows, journal_types)
		plan = built["plan"]

		self.assertEqual(len(plan[PAYABLE_DOCTYPE]), 2)  # AC · A-1 and AC · X-1
		self.assertEqual(len(plan[RECEIVABLE_DOCTYPE]), 2)  # VT · V-1 and VT · X-1
		self.assertEqual(len(plan[TREASURY_DOCTYPE]), 1)  # BQ · B-1 is Treasury
		self.assertEqual(len(plan.get(None, [])), 0)

		self.assertEqual(
			built["per_journal"]["AC"],
			{PAYABLE_DOCTYPE: 2, RECEIVABLE_DOCTYPE: 0, TREASURY_DOCTYPE: 0, "unclassified": 0},
		)
		self.assertEqual(
			built["per_journal"]["VT"],
			{PAYABLE_DOCTYPE: 0, RECEIVABLE_DOCTYPE: 2, TREASURY_DOCTYPE: 0, "unclassified": 0},
		)
		self.assertEqual(
			built["per_journal"]["BQ"],
			{PAYABLE_DOCTYPE: 0, RECEIVABLE_DOCTYPE: 0, TREASURY_DOCTYPE: 1, "unclassified": 0},
		)

		# the groups carry their rows untouched
		payable_rows = [
			row["name"] for _journal, mvt, group in plan[PAYABLE_DOCTYPE] if mvt == "A-1" for row in group
		]
		self.assertEqual(payable_rows, ["L1", "L2"])

	def test_unknown_accounts_classify_as_no_auxiliary(self):
		rows = [
			ledger_row("L1", "AC", "A-9", "999999", debit=10),
			ledger_row("L2", "AC", "A-9", "532000", credit=10),
		]
		built = plan_of(rows, {"AC": "Achat"})
		self.assertEqual(len(built["plan"][TREASURY_DOCTYPE]), 1)
		self.assertEqual(len(built["plan"].get(None, [])), 0)

	def test_split_unbalanced_multiref_group(self):
		rows = [
			# Sub-entry 1: ref REF-1, 2026-03-01
			ledger_row("L1", "BQ", "M-1", "532000", debit=100, ref_doc="REF-1", posting_date=date(2026, 3, 1)),
			ledger_row("L2", "BQ", "M-1", "401000", credit=100, ref_doc="REF-1", posting_date=date(2026, 3, 1)),
			# Sub-entry 2: ref REF-2, 2026-03-02
			ledger_row("L3", "BQ", "M-1", "532000", debit=50, ref_doc="REF-2", posting_date=date(2026, 3, 2)),
			ledger_row("L4", "BQ", "M-1", "411000", credit=50, ref_doc="REF-2", posting_date=date(2026, 3, 2)),
		]
		built = materialize_plan(rows, {"BQ": "Banque"}, ACCOUNT_NUMBERS, split_multiref=True)
		self.assertEqual(len(built["groups_with_multiple_refs_or_dates"]), 1)
		# Sub-entry 1 has 401000 -> PAYABLE_DOCTYPE
		# Sub-entry 2 has 411000 -> RECEIVABLE_DOCTYPE
		self.assertEqual(len(built["plan"][PAYABLE_DOCTYPE]), 1)
		self.assertEqual(len(built["plan"][RECEIVABLE_DOCTYPE]), 1)
		self.assertEqual(built["plan"][PAYABLE_DOCTYPE][0][1], "M-1-1")
		self.assertEqual(built["plan"][RECEIVABLE_DOCTYPE][0][1], "M-1-2")


class TestBuildEntryPayload(unittest.TestCase):
	def test_payload_keeps_mvt_dates_lines_and_flags(self):
		rows = [
			ledger_row("L1", "AC", "A-1", "601000", debit=100, libelle="Achat marchandise", ref_doc="FR-12"),
			ledger_row("L2", "AC", "A-1", "445600", debit=19, tresorerie="OPS-1"),
			ledger_row("L3", "AC", "A-1", "401000", credit=119),
		]
		parent, lines = build_entry_payload(PAYABLE_DOCTYPE, "AC", "A-1", date(2026, 3, 15), "GL-TEST", rows)
		self.assertEqual(parent["name"], "A-1")
		self.assertEqual(parent["mvt"], "A-1")
		self.assertEqual(parent["date_operation"], date(2026, 3, 15))
		self.assertEqual(parent["mois"], "03")  # zero-padded, like derive_period
		self.assertEqual(parent["jour"], 15)
		self.assertEqual(parent["total_debit"], 119.0)
		self.assertEqual(parent["total_credit"], 119.0)
		self.assertEqual(parent["solde"], 0.0)
		self.assertEqual(parent["status"], "Comptabilise")  # already posted
		self.assertEqual(parent["imported"], 1)
		self.assertEqual(parent["import_batch"], "GL-TEST")
		self.assertEqual(parent["ref_doc"], "FR-12")  # first non-empty piece
		self.assertEqual(parent["entreprise"], "ENT-1")
		self.assertEqual(parent["exercice"], "EX-2026")

		self.assertEqual(len(lines), 3)
		self.assertEqual([line["idx"] for line in lines], [1, 2, 3])
		self.assertEqual([line["account"] for line in lines], ["601000", "445600", "401000"])
		self.assertEqual([line["libelle"] for line in lines], ["Achat marchandise", "", ""])
		self.assertEqual(lines[1]["tresorerie"], "OPS-1")
		self.assertEqual([line["debit"] for line in lines], [100.0, 19.0, 0.0])
		self.assertEqual([line["credit"] for line in lines], [0.0, 0.0, 119.0])

	def test_rounding_stays_at_three_decimals(self):
		rows = [
			ledger_row("L1", "AC", "A-2", "601000", debit=10.0005),
			ledger_row("L2", "AC", "A-2", "401000", credit=10.0005),
		]
		parent, lines = build_entry_payload(PAYABLE_DOCTYPE, "AC", "A-2", date(2026, 3, 15), "GL-TEST", rows)
		self.assertEqual(parent["total_debit"], 10.001)
		self.assertEqual(parent["solde"], 0.0)
		self.assertEqual(lines[0]["debit"], 10.001)


class TestPlanPerformance(unittest.TestCase):
	def test_32k_rows_through_the_plan(self):
		"""~32,175 imported rows (the real Annuelle import) → several
		thousand entries: the pure plan must stay far below the background
		job budget (the DB inserts are timed separately, against a site)."""
		rows = []
		index = 0
		for mvt_index in range(10725):  # 3 rows per movement → 32,175 rows
			journal = "AC" if mvt_index % 2 == 0 else "VT"
			aux = "401000" if journal == "AC" else "411000"
			rows.append(ledger_row(f"L{index}", journal, f"M-{mvt_index}", "601000", debit=100))
			index += 1
			rows.append(ledger_row(f"L{index}", journal, f"M-{mvt_index}", aux, credit=100))
			index += 1
			rows.append(ledger_row(f"L{index}", journal, f"M-{mvt_index}", "532000", debit=0.01, credit=0.0))
			index += 1
		rows.append(ledger_row("L-last", "BQ", "AN-1", "101000", credit=1))
		rows.append(ledger_row("L-last2", "BQ", "AN-1", "112000", debit=1))

		start = time.perf_counter()
		built = materialize_plan(rows, {"AC": "Achat", "VT": "Vente", "BQ": "Banque"}, ACCOUNT_NUMBERS)
		elapsed = time.perf_counter() - start

		self.assertEqual(len(built["plan"][PAYABLE_DOCTYPE]), 5363)
		self.assertEqual(len(built["plan"][RECEIVABLE_DOCTYPE]), 5362)
		self.assertEqual(len(built["plan"][TREASURY_DOCTYPE]), 1)
		self.assertEqual(len(built["plan"].get(None, [])), 0)
		self.assertEqual(len(rows), 32177)
		print(f"\nmaterialize_plan over {len(rows)} rows / 10727 groups: {elapsed * 1000:.0f} ms")
		self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
	unittest.main(verbosity=2)
