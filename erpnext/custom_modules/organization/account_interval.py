# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Chart-of-Account number interval matching, shared by everything that
selects ledger accounts from a number range or a number prefix: the Ledger
Data report's "Intervalle des comptes" / "Saisie libre" filters, the
Déclaration Mensuelle configuration (comptes_brut / comptes_retenu) and its
engine.

Pure and frappe-free: the callers hand over bare account numbers, never
Chart of Account documents.

The semantics are the Ledger Data report's, kept verbatim:
- a LOWER bound matches ``num >= lower`` or a prefix (``num.startswith(lower)``),
- an UPPER bound matches ``num <= upper`` or a prefix — so a range written
  ``432000-4`` still catches ``4320001``.
An interval with no upper bound (the declaration config's optional
``compte_a``) degrades to the single-token rule: equality or prefix.
"""

from __future__ import annotations


def match_lower(acc_num: str, lower: str) -> bool:
	return acc_num >= lower or acc_num.startswith(lower)


def match_upper(acc_num: str, upper: str) -> bool:
	return acc_num <= upper or acc_num.startswith(upper)


def match_interval(account_number: str, compte_de: str, compte_a: str = "") -> bool:
	"""One interval row: [compte_de, compte_a] when an upper bound is given,
	otherwise the single-token rule (equality or prefix) on compte_de."""
	number = account_number or ""
	de = (compte_de or "").strip()
	a = (compte_a or "").strip()
	if not number or not de:
		return False
	if not a:
		return number == de or number.startswith(de)
	return match_lower(number, de) and match_upper(number, a)


def match_intervals(account_number: str, intervals: list) -> bool:
	"""Any one of the (compte_de, compte_a) tuples matches."""
	return any(match_interval(account_number, de, a) for de, a in intervals)


def matched_accounts(coa_rows: list, intervals: list) -> list[str]:
	"""The Chart of Account names whose account_number falls in the intervals.
	``coa_rows`` carry name + account_number (a frappe.get_all of Chart of
	Account, or any mapping with the same keys)."""
	return [
		row["name"]
		for row in coa_rows
		if match_intervals(row.get("account_number") or "", intervals)
	]
