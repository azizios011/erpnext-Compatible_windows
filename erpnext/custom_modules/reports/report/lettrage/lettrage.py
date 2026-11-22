# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Lettrage — the "Saisie du lettrage" tool as a Script Report over the
Ecriture Comptable ledger (the lettrage Page and the Single "Lettrage"
doctype shared the /app/lettrage slug; frappe's router resolved the doctype
first and the sidebar opened an empty form — both are gone).

The account panel, the tabs and the header buttons are client-side
(lettrage.js on frappe.query_reports["Lettrage"]); this module serves ONE
page of lines for the selected account — the old get_lines logic — with the
header stats as report_summary cards over the whole filtered set. Every
query is scoped to the dock context's Entreprise and Exercice. The write
endpoints (lettering, pointage, auto passes) live in lettrage_api.py.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.lettrage_api import peek_next_code
from erpnext.custom_modules.reports.report_common import (
	REPORT_CURRENCY,
	check_ledger_read_permission,
)

LEDGER = "Ecriture Comptable"

STATUS_MAP = {
	"Non lettrees": "Non lettre",
	"Partielles": "Partiel",
	"Lettrees": "Lettre",
}


def execute(filters=None) -> tuple:
	"""Standard Script Report entry point: columns, ONE PAGE of lines for the
	selected account, no chart, and the summary cards over ALL filtered rows
	(the totals stay global while the table pages). Without an account the
	report stays empty and points at the left panel."""
	filters = filters or {}
	context = require_context()
	check_ledger_read_permission()
	columns = get_columns()

	account = (filters.get("account") or "").strip()
	if not account:
		return columns, [], _("Pick an account on the left."), None, []

	rows, stats = _get_line_rows(filters, context, account)
	summary = _get_report_summary(context, account, stats)
	rows, message = _paginate(rows, filters)
	return columns, rows, message, None, summary


def get_columns() -> list[dict]:
	"""The datatable columns (the row checkbox comes from the client-side
	checkboxColumn datatable option, POINTE is rendered by the JS formatter)."""
	return [
		{"label": _("Mvt"), "fieldname": "mvt", "fieldtype": "Dynamic Link", "options": "source_entry_doctype", "width": 110},
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Data", "width": 90},
		{"label": _("Jrn"), "fieldname": "journal", "fieldtype": "Data", "width": 70},
		{"label": _("N° Piece"), "fieldname": "ref_doc", "fieldtype": "Data", "width": 110},
		{"label": _("Libelle"), "fieldname": "libelle", "fieldtype": "Data", "width": 220},
		{"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 120},
		{"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 120},
		{"label": _("Solde Prog."), "fieldname": "solde_prog", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Lettre"), "fieldname": "lettrage", "fieldtype": "Data", "width": 90},
		{"label": _("Pointe"), "fieldname": "pointe", "fieldtype": "Check", "width": 70},
	]


def _get_line_rows(filters: dict, context: dict, account: str) -> tuple[list[dict], dict]:
	"""The old get_lines logic: every matching line of one account oldest
	first with a running Solde per line, plus the header stats over the whole
	filtered set (not just the page)."""
	ledger_filters: list[list] = [
		["entreprise", "=", context["entreprise"]],
		["exercice", "=", context["exercice"]],
		["account", "=", account],
	]

	tab = filters.get("tab") or "Non lettrees"
	if tab in STATUS_MAP:
		ledger_filters.append(["lettrage_status", "=", STATUS_MAP[tab]])

	if filters.get("from_date"):
		ledger_filters.append(["posting_date", ">=", filters["from_date"]])
	if filters.get("to_date"):
		ledger_filters.append(["posting_date", "<=", filters["to_date"]])
	if filters.get("journal"):
		ledger_filters.append(["journal", "=", filters["journal"]])
	if filters.get("libelle"):
		ledger_filters.append(["libelle", "like", f"%{filters['libelle']}%"])

	or_filters: list[list] = []
	if filters.get("amount_min"):
		or_filters.append(["debit", ">=", flt(filters["amount_min"])])
		or_filters.append(["credit", ">=", flt(filters["amount_min"])])
	if filters.get("amount_max"):
		or_filters.append(["debit", "<=", flt(filters["amount_max"])])
		or_filters.append(["credit", "<=", flt(filters["amount_max"])])

	all_rows = frappe.get_all(
		LEDGER,
		filters=ledger_filters,
		or_filters=or_filters,
		fields=[
			"name",
			"posting_date",
			"journal",
			"mvt",
			"ref_doc",
			"libelle",
			"debit",
			"credit",
			"devise",
			"lettrage",
			"lettrage_status",
			"pointe",
			"source_entry_doctype",
			"source_entry",
			"source_doctype",
			"source_name",
		],
		order_by="posting_date asc, creation asc",
	)

	running = 0.0
	for row in all_rows:
		running = flt(running + flt(row.debit) - flt(row.credit), 3)
		row["solde_prog"] = running

	stats = {
		"solde": running,
		"non_lettre": sum(1 for row in all_rows if row.lettrage_status == "Non lettre"),
		"lignes_a_lettrer": sum(
			1 for row in all_rows if row.lettrage_status in ("Non lettre", "Partiel")
		),
	}

	for row in all_rows:
		row["date"] = getdate(row.posting_date).strftime("%d/%m/%Y") if row.posting_date else ""
		row["side"] = "D" if row.solde_prog >= 0 else "C"

	return all_rows, stats


def _get_report_summary(context: dict, account: str, stats: dict) -> list[dict]:
	"""The right header of the Axeane screen: SOLDE / NON LETTRE / LIGNES A
	LETTRER / PROCHAINE LETTRE, over the whole filtered set."""
	return [
		{
			"label": _("Solde"),
			"value": flt(stats["solde"], 3),
			"datatype": "Currency",
			"currency": REPORT_CURRENCY,
			"precision": 3,
			"indicator": "Blue",
		},
		{"label": _("Non lettre"), "value": stats["non_lettre"], "datatype": "Int", "indicator": "Orange"},
		{"label": _("Lignes a lettrer"), "value": stats["lignes_a_lettrer"], "datatype": "Int", "indicator": "Orange"},
		{
			"label": _("Prochaine lettre"),
			"value": peek_next_code(context["entreprise"], account),
			"datatype": "Data",
			"indicator": "Grey",
		},
	]


def _paginate(rows: list[dict], filters: dict) -> tuple[list[dict], str]:
	"""Server-side paging for the list: the client renders one page of rows;
	the summary above stays global over the whole filtered set. The message
	wording feeds the bottom bar (five integers, positional)."""
	total = len(rows)
	page_size = cint(filters.get("page_size")) or 25
	page_size = min(max(page_size, 1), 250)
	page = max(cint(filters.get("page")), 1)
	pages = max((total + page_size - 1) // page_size, 1)
	page = min(page, pages)
	start = (page - 1) * page_size
	page_rows = rows[start : start + page_size]
	if not total:
		return [], ""
	message = _("Showing {0} - {1} of {2} rows (page {3} of {4}).").format(
		start + 1, start + len(page_rows), total, page, pages
	)
	return page_rows, message
