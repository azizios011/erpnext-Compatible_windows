# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Balance generale — the trial balance per account over the Ecriture
Comptable ledger.

One row per account that has ledger rows up to the period end: opening
balances (rows from the Exercice start up to the day before the period),
movements inside the period, and the netted closing side (a net debit
balance goes to Debit, a net credit balance to Credit — never both). Scoped
to the dock context's Entreprise and Exercice like Ledger Data; the period
is clamped to the Exercice's dates. The account set follows the balance
type (General / Auxiliaire Client 411 / Auxiliaire Fournisseur 401) and the
account_from / account_to number range.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import (
	_check_permission,
	_resolve_period,
	AUX_CLIENT_PREFIX,
	AUX_FOURNISSEUR_PREFIX,
	BALANCE_TOLERANCE,
)

LEDGER_DOCTYPE = "Ecriture Comptable"

AUX_PREFIX_BY_TYPE = {
	"Auxiliaire Client": AUX_CLIENT_PREFIX,
	"Auxiliaire Fournisseur": AUX_FOURNISSEUR_PREFIX,
}


def execute(filters=None) -> tuple:
	filters = filters or {}
	context = require_context()
	_check_permission()
	from_date, to_date = _resolve_period(filters, context)
	exercice_debut = getdate(context["date_debut"]) if context.get("date_debut") else None
	devise = filters.get("devise") or "TND"

	# the account set: balance type (prefix) + the account_from / account_to
	# number range, resolved against the Entreprise's chart
	chart = frappe.get_all(
		"Chart of Account",
		filters={"entreprise": context["entreprise"], "is_group": 0, "disabled": 0},
		fields=["name", "account_number", "account_name"],
	)
	accounts = _selected_accounts(chart, filters)

	if not accounts:
		return get_columns(devise), [], None, None, _movement_summary([], devise)

	# every ledger row of the Exercice up to the period end: the opening side
	# is computed from the rows before the period, the movement from the rows
	# inside it
	ledger_filters = [
		["entreprise", "=", context["entreprise"]],
		["exercice", "=", context["exercice"]],
		["devise", "=", devise],
		["account", "in", sorted(accounts)],
	]
	if exercice_debut:
		ledger_filters.append(["posting_date", ">=", exercice_debut])
	else:
		ledger_filters.append(["posting_date", ">=", from_date])
	ledger_filters.append(["posting_date", "<=", to_date])

	rows = frappe.get_all(
		LEDGER_DOCTYPE,
		filters=ledger_filters,
		fields=["name", "posting_date", "account", "debit", "credit"],
	)

	aggregated = _aggregate(rows, accounts, from_date, to_date, chart)
	out = _balance_rows(aggregated, filters, devise)

	return get_columns(devise), out, None, None, _movement_summary(out, devise)


def _selected_accounts(chart: list[dict], filters: dict) -> dict:
	"""The accounts selected by the balance type (prefix) and the
	account_from / account_to number range: {account name: row}."""
	prefix = AUX_PREFIX_BY_TYPE.get(filters.get("balance_type") or "General")
	account_from = (filters.get("account_from") or "").strip()
	account_to = (filters.get("account_to") or "").strip()
	selected: dict[str, dict] = {}
	for row in chart:
		number = (row.account_number or "").strip()
		if not number:
			continue
		if prefix and not number.startswith(prefix):
			continue
		if account_from and number < account_from:
			continue
		if account_to and number > account_to:
			continue
		selected[row.name] = row
	return selected


def _aggregate(rows: list[dict], accounts: dict[str, dict], from_date, to_date) -> dict:
	"""Per-account opening / movement sums. Rows before the period build the
	opening side; rows inside it build the movement."""
	from_date = getdate(from_date)
	to_date = getdate(to_date)
	for row in rows:
		entry = accounts.setdefault(
			row.account,
			{"number": "", "libelle": "", "opening_debit": 0.0, "opening_credit": 0.0, "movement_debit": 0.0, "movement_credit": 0.0},
		)
		posting = getdate(row.posting_date) if row.posting_date else None
		if posting and posting < from_date:
			entry["opening_debit"] = flt(entry["opening_debit"] + flt(row.debit), 3)
			entry["opening_credit"] = flt(entry["opening_credit"] + flt(row.credit), 3)
		else:
			entry["movement_debit"] = flt(entry["movement_debit"] + flt(row.debit), 3)
			entry["movement_credit"] = flt(entry["movement_credit"] + flt(row.credit), 3)
	return accounts


def _balance_rows(aggregated: dict, filters: dict, devise: str) -> list[dict]:
	"""The report rows: netted closing side, extract_type filter applied,
	sorted by account number."""
	extract_type = filters.get("extract_type") or "Tous les comptes"
	out: list[dict] = []
	for account in sorted(aggregated, key=lambda a: (aggregated[a]["number"], a)):
		entry = aggregated[account]
		opening_net = flt(entry["opening_debit"] - entry["opening_credit"], 3)
		mov_net = flt(entry["movement_debit"] - entry["movement_credit"], 3)
		closing_net = flt(opening_net + mov_net, 3)
		if extract_type == "Comptes mouvementes" and mov_net == 0:
			continue
		if extract_type == "Comptes non soldes" and abs(closing_net) <= BALANCE_TOLERANCE:
			continue
		out.append(
			{
				"compte": " ".join(x for x in (entry["number"], entry["libelle"]) if x) or account,
				"opening_debit": flt(opening_net, 3) if opening_net > 0 else 0.0,
				"opening_credit": flt(-opening_net, 3) if opening_net < 0 else 0.0,
				"movement_debit": flt(entry["movement_debit"], 3),
				"movement_credit": flt(entry["movement_credit"], 3),
				# the netted balance goes to one side only, never both
				"closing_debit": flt(closing_net, 3) if closing_net > 0 else 0.0,
				"closing_credit": flt(-closing_net, 3) if closing_net < 0 else 0.0,
				"devise": devise,
			}
		)
	return out


def get_columns(devise: str) -> list[dict]:
	return [
		{"label": _("Compte"), "fieldname": "compte", "fieldtype": "Data", "width": 280},
		{"label": _("Opening Debit"), "fieldname": "opening_debit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Opening Credit"), "fieldname": "opening_credit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Movement Debit"), "fieldname": "movement_debit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Movement Credit"), "fieldname": "movement_credit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Closing Debit"), "fieldname": "closing_debit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Closing Credit"), "fieldname": "closing_credit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
	]


def _movement_summary(rows: list[dict], devise: str) -> list[dict]:
	"""The three summary cards over the MOVEMENT columns of the shown rows."""
	total_debit = flt(sum(flt(r["movement_debit"]) for r in rows), 3)
	total_credit = flt(sum(flt(r["movement_credit"]) for r in rows), 3)
	solde = flt(total_debit - total_credit, 3)
	return [
		{"label": _("Total Debit"), "value": total_debit, "datatype": "Currency", "currency": devise, "precision": 3, "indicator": "Green"},
		{"label": _("Total Credit"), "value": total_credit, "datatype": "Currency", "currency": devise, "precision": 3, "indicator": "Red"},
		{"label": _("Solde"), "value": solde, "datatype": "Currency", "currency": devise, "precision": 3, "indicator": "Blue"},
	]
