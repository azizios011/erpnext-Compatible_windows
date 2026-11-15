# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Ledger Data — Axeane's "Grand Livre" over the Ecriture Comptable ledger.

The LIST view is the native report page (filters, datatable, bottom
summary). The Grille builder (rows grouped per account with opening
balances and running totals) stays here: it will feed the OnlyOffice-based
PDF and XLSX views later — PDF and XLSX are placeholders in the client.
"""

from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import (
	AUX_CLIENT_PREFIX,
	AUX_FOURNISSEUR_PREFIX,
	BALANCE_TOLERANCE,
	REPORT_CURRENCY,
	as_list,
	check_ledger_read_permission,
	exercice_year,
	resolve_period,
)

LEDGER_DOCTYPE = "Ecriture Comptable"


def execute(filters=None) -> tuple:
	"""Standard Script Report entry point: columns, rows, no chart,
	report summary over ALL filtered rows. Every query is scoped to the
	dock context's Entreprise and Exercice."""
	filters = filters or {}
	context = require_context()
	if filters.get("view") == "Grille":
		columns = _get_grille_columns()
		rows = _get_grille_rows(filters, context)
		# the groups carry their own totals: no datatable total row
		# add_total_row is 0: the datatable never builds a total row anyway
		return columns, rows, None, None, _get_report_summary(_flat_rows(rows))
	columns = get_columns()
	rows = _get_rows(filters, context)
	return columns, rows, None, None, _get_report_summary(rows)


def _account_filter(filters: dict) -> list[str]:
	"""The Chart of Account rows selected by the grand-livre type."""
	ledger_type = filters.get("ledger_type") or "General"
	if ledger_type == "Auxiliaire Client":
		prefix = AUX_CLIENT_PREFIX
	elif ledger_type == "Auxiliaire Fournisseur":
		prefix = AUX_FOURNISSEUR_PREFIX
	else:
		return []
	return frappe.get_all(
		"Chart of Account",
		filters={"account_number": ("like", f"{prefix}%")},
		pluck="name",
	)


def _ledger_filters(filters: dict, context: dict, from_date: date, to_date: date) -> list[list]:
	out = [
		["posting_date", ">=", from_date],
		["posting_date", "<=", to_date],
		# the context's Entreprise and Exercice, always
		["entreprise", "=", context["entreprise"]],
		["exercice", "=", context["exercice"]],
	]
	if filters.get("journal"):
		out.append(["journal", "in", as_list(filters["journal"])])
	if filters.get("mvt"):
		out.append(["mvt", "in", as_list(filters["mvt"])])
	if filters.get("devise"):
		out.append(["devise", "=", filters["devise"]])
	lettrage = filters.get("lettrage") or "Tous"
	if lettrage == "Lettre":
		out.append(["lettrage", "is", "set"])
	elif lettrage == "Non lettre":
		out.append(["lettrage", "is", "not set"])
	accounts = _account_filter(filters)
	if accounts:
		out.append(["account", "in", accounts])
	elif (filters.get("ledger_type") or "General") != "General":
		# an auxiliary type whose prefix matched no account: nothing to show
		out.append(["name", "=", ""])
	return out


def _get_rows(filters: dict, context: dict) -> list[dict]:
	check_ledger_read_permission()
	from_date, to_date = resolve_period(filters, context)
	rows = frappe.get_all(
		LEDGER_DOCTYPE,
		filters=_ledger_filters(filters, context, from_date, to_date),
		fields=[
			"name",
			"posting_date",
			"journal",
			"mvt",
			"account",
			"libelle",
			"debit",
			"credit",
			"devise",
			"ref_doc",
			"tresorerie",
			"lettrage",
			"source_entry_doctype",
			"source_entry",
			"source_doctype",
			"source_name",
		],
	)
	if not rows:
		return []

	extract_type = filters.get("extract_type") or "Tous les comptes"
	if extract_type == "Comptes non soldes":
		balance: dict = {}
		for row in rows:
			balance[row.account] = balance.get(row.account, 0.0) + flt(row.debit) - flt(row.credit)
		rows = [row for row in rows if abs(balance.get(row.account, 0.0)) > BALANCE_TOLERANCE]
	# "Comptes mouvementes" and "Tous les comptes" both show the period's rows

	numbers = frappe.get_all(
		"Chart of Account",
		filters={"name": ("in", {row.account for row in rows})},
		fields=["name", "account_number", "account_name"],
	)
	display = {
		a.name: " ".join(x for x in (a.account_number, a.account_name) if x) or a.name
		for a in numbers
	}
	for row in rows:
		row["compte_comptable"] = display.get(row.account, row.account)

	rows.sort(key=lambda r: (display.get(r.account, ""), getdate(r.posting_date), r.mvt or ""))
	return rows


def get_columns() -> list[dict]:
	return [
		{"label": _("Mvt"), "fieldname": "mvt", "fieldtype": "Dynamic Link", "options": "source_entry_doctype", "width": 130},
		{"label": _("Jrn"), "fieldname": "journal", "fieldtype": "Data", "width": 70},
		{"label": _("Compte Comptable"), "fieldname": "compte_comptable", "fieldtype": "Data", "width": 230},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Libelle"), "fieldname": "libelle", "fieldtype": "Data", "width": 250},
		{"label": _("Tresorerie"), "fieldname": "tresorerie", "fieldtype": "Link", "options": "Operation Tresorerie", "width": 140},
		{"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Lettrage"), "fieldname": "lettrage", "fieldtype": "Data", "width": 90},
		{"label": _("N° Doc"), "fieldname": "ref_doc", "fieldtype": "Data", "width": 120},
		{"label": _("Piece"), "fieldname": "source_name", "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 150},
	]


def _get_grille_columns() -> list[dict]:
	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Data", "width": 100},
		{"label": _("Mvt"), "fieldname": "mvt", "fieldtype": "Dynamic Link", "options": "source_entry_doctype", "width": 130},
		{"label": _("Libelle"), "fieldname": "libelle", "fieldtype": "Data", "width": 260},
		{"label": _("Jrn"), "fieldname": "journal", "fieldtype": "Data", "width": 70},
		{"label": _("Ref"), "fieldname": "ref_doc", "fieldtype": "Data", "width": 120},
		{"label": _("Tresorerie"), "fieldname": "tresorerie", "fieldtype": "Link", "options": "Operation Tresorerie", "width": 140},
		{"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Lettrage"), "fieldname": "lettrage", "fieldtype": "Data", "width": 90},
		{"label": _("Solde"), "fieldname": "solde", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 140},
	]


def _get_report_summary(rows: list[dict]) -> list[dict]:
	total_debit = flt(sum(flt(r["debit"]) for r in rows), 3)
	total_credit = flt(sum(flt(r["credit"]) for r in rows), 3)
	solde = flt(total_debit - total_credit, 3)
	return [
		{"label": _("Total Debit"), "value": total_debit, "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Green"},
		{"label": _("Total Credit"), "value": total_credit, "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Red"},
		{"label": _("Solde"), "value": solde, "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Blue"},
	]


def _flat_rows(grille_rows: list[dict]) -> list[dict]:
	"""Entry rows only (no header/opening/total markers) for the summary."""
	return [row for row in grille_rows if row.get("row_type") == "entry"]


def _get_grille_rows(filters: dict, context: dict) -> list[dict]:
	"""Rows grouped per account: a bold header, the opening balance
	(movements from the Exercice start up to the day before from_date), the
	entries with a running Solde, and a bold totals row per account."""
	rows = _get_rows(filters, context)
	if not rows:
		return []

	from_date, to_date = resolve_period(filters, context)
	year = exercice_year(context)

	accounts: list[str] = []
	by_account: dict[str, list] = {}
	for row in rows:
		by_account.setdefault(row.account, []).append(row)
		if row.account not in accounts:
			accounts.append(row.account)

	openings: dict[str, float] = {}
	exercice_debut = getdate(context["date_debut"]) if context.get("date_debut") else None
	if exercice_debut and from_date > exercice_debut:
		opening_until = from_date - timedelta(days=1)
		# same Entreprise/Exercice scope as the main query, escaped inline
		opening_rows = frappe.db.sql(
			"""select account, sum(debit) - sum(credit) as balance
				from `tabEcriture Comptable`
				where entreprise = %(entreprise)s
					and exercice = %(exercice)s
					and posting_date >= %(exercice_start)s
					and posting_date <= %(until)s
				group by account""",
			{
				"entreprise": context["entreprise"],
				"exercice": context["exercice"],
				"exercice_start": exercice_debut,
				"until": opening_until,
			},
			as_dict=True,
		)
		for row in opening_rows:
			openings[row.account] = flt(row.balance, 3)

	out: list[dict] = []
	for account in accounts:
		account_rows = by_account[account]
		display = account_rows[0].get("compte_comptable") or account
		solde = openings.get(account, 0.0)
		total_debit = total_credit = 0.0
		out.append({"row_type": "header", "date": display})
		if openings:
			out.append(
				{
					"row_type": "opening",
					"date": opening_until.strftime("%d/%m/%Y"),
					"libelle": _("Solde a nouveau / Report"),
					"solde": solde,
				}
			)
		for row in account_rows:
			debit, credit = flt(row.debit), flt(row.credit)
			solde = flt(solde + debit - credit, 3)
			total_debit = flt(total_debit + debit, 3)
			total_credit = flt(total_credit + credit, 3)
			out.append(
				{
					"row_type": "entry",
					"date": getdate(row.posting_date).strftime("%d/%m/%Y"),
					"mvt": row.mvt,
					"libelle": row.libelle,
					"journal": row.journal,
					"ref_doc": row.ref_doc,
					"tresorerie": row.tresorerie,
					"lettrage": row.lettrage,
					"debit": debit,
					"credit": credit,
					"solde": solde,
					"source_entry_doctype": row.source_entry_doctype,
					"source_doctype": row.source_doctype,
					"source_name": row.source_name,
				}
			)
		out.append(
			{
				"row_type": "total",
				"date": _("Totaux {0}").format(display),
				"debit": total_debit,
				"credit": total_credit,
				"solde": flt(openings.get(account, 0.0) + total_debit - total_credit, 3),
			}
		)
	return out
