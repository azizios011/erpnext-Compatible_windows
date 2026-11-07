# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Ledger Data — Axeane's "Grand Livre" over the Ecriture Comptable ledger.

The standard report table is the list view; get_pdf_view / get_pdf_view_all
render the "Rapport PDF" style pages (HTML paper — the real PDF/export comes
later through the Print Designer path).
"""

import json
import os
from datetime import date, timedelta
from math import ceil
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, getdate, nowdate

# auxiliary ledgers are the client / supplier account-number prefixes
AUX_CLIENT_PREFIX = "411"
AUX_FOURNISSEUR_PREFIX = "401"

ROWS_PER_PAGE = 45
REPORT_CURRENCY = "TND"
LEDGER_DOCTYPE = "Ecriture Comptable"

MONTHS_FR = {
	"Janvier": 1,
	"Fevrier": 2,
	"Mars": 3,
	"Avril": 4,
	"Mai": 5,
	"Juin": 6,
	"Juillet": 7,
	"Aout": 8,
	"Septembre": 9,
	"Octobre": 10,
	"Novembre": 11,
	"Decembre": 12,
}

QUARTER_MONTHS = {"T1": (1, 3), "T2": (4, 6), "T3": (7, 9), "T4": (10, 12)}


def execute(filters=None) -> tuple:
	"""Standard Script Report entry point: columns, rows, no chart,
	report summary over ALL filtered rows."""
	filters = filters or {}
	columns = get_columns()
	rows = _get_rows(filters)
	return columns, rows, None, None, _get_report_summary(rows)


def get_ledger_years() -> list[str]:
	"""Exercice options: the years present in the ledger, current year last."""
	if not frappe.db.exists("DocType", LEDGER_DOCTYPE):
		return [nowdate()[:4]]
	years = frappe.get_all(
		LEDGER_DOCTYPE,
		fields=["distinct year(posting_date) as year"],
		order_by="year asc",
		pluck="year",
	)
	years = [str(y) for y in years if y]
	current = nowdate()[:4]
	if current not in years:
		years.append(current)
	return years


def _check_permission() -> None:
	if not frappe.has_permission(LEDGER_DOCTYPE, "read"):
		frappe.throw(_("Not permitted to read the ledger"), frappe.PermissionError)


def _resolve_period(filters: dict) -> tuple[date, date]:
	"""Every period filter resolves to one (from_date, to_date) pair."""
	period_type = filters.get("period_type") or "Mensuelle"
	year = int(filters.get("year") or nowdate()[:4])
	if period_type == "Personnalisee":
		return getdate(filters.get("from_date")), getdate(filters.get("to_date"))
	if period_type == "Trimestrielle":
		first, last = QUARTER_MONTHS[filters.get("quarter") or "T1"]
		return date(year, first, 1), date(year, last, 31 if last in (1, 3, 7, 8, 10, 12) else 30)
	if period_type == "Annuelle":
		return date(year, 1, 1), date(year, 12, 31)
	# Mensuelle
	month = MONTHS_FR.get(filters.get("month") or "", 1)
	next_month = date(year + (month == 12), (month % 12) + 1, 1)
	return date(year, month, 1), next_month - timedelta(days=1)


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


def _ledger_filters(filters: dict, from_date: date, to_date: date) -> list[list]:
	out = [["posting_date", ">=", from_date], ["posting_date", "<=", to_date]]
	if filters.get("company"):
		out.append(["company", "=", filters["company"]])
	if filters.get("journal"):
		out.append(["journal", "in", _as_list(filters["journal"])])
	if filters.get("mvt"):
		out.append(["mvt", "in", _as_list(filters["mvt"])])
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


def _as_list(value: Any) -> list:
	"""MultiSelectList values arrive as lists or comma-joined strings."""
	if isinstance(value, (list, tuple)):
		return [v for v in value if v]
	return [v.strip() for v in str(value).split(",") if v.strip()]


def _get_rows(filters: dict) -> list[dict]:
	_check_permission()
	from_date, to_date = _resolve_period(filters)
	rows = frappe.get_all(
		LEDGER_DOCTYPE,
		filters=_ledger_filters(filters, from_date, to_date),
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
		rows = [row for row in rows if abs(balance.get(row.account, 0.0)) > 0.0005]
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
		{"label": _("Tresorerie"), "fieldname": "tresorerie", "fieldtype": "Link", "options": "Chart of Account", "width": 140},
		{"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": "devise", "precision": "3", "width": 130},
		{"label": _("Lettrage"), "fieldname": "lettrage", "fieldtype": "Data", "width": 90},
		{"label": _("N° Doc"), "fieldname": "ref_doc", "fieldtype": "Data", "width": 120},
		{"label": _("Piece"), "fieldname": "source_name", "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 150},
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


# ── the "Rapport PDF" (HTML paper) ───────────────────────────────────────────


def get_report_header(company: str) -> dict:
	"""The page header. Kept as one function so it can be repointed from the
	core Company doctype to the custom Entreprise doctype later."""
	tax_id = frappe.db.get_value("Company", company, "tax_id") if company else None
	return {"company_name": company or "", "tax_id": tax_id or ""}


@frappe.whitelist()
def get_pdf_view(filters: str, layout: str, page: int) -> dict:
	"""One viewer page (~ROWS_PER_PAGE visual rows) of the Grand Livre."""
	_check_permission()
	parsed = json.loads(filters or "{}")
	parsed["page"] = int(page or 1)
	return _render_pdf(parsed, str(layout or "Simple"), int(page or 1))


@frappe.whitelist()
def get_pdf_view_all(filters: str, layout: str) -> dict:
	"""The whole document, for "Imprimer" (A4 print CSS, repeated thead)."""
	_check_permission()
	parsed = json.loads(filters or "{}")
	return _render_pdf(parsed, str(layout or "Simple"), page=None)


def _render_pdf(filters: dict, layout: str, page: int | None) -> dict:
	from_date, to_date = _resolve_period(filters)
	rows = _get_rows(filters)
	year = int(filters.get("year") or nowdate()[:4])
	groups = _group_rows(rows, from_date, to_date, year)
	pages = _paginate(groups, ROWS_PER_PAGE)
	total_pages = max(len(pages), 1)
	current = min(max(page or 1, 1), total_pages) if page else None
	if page:
		shown = pages[current - 1] if pages else []
	else:
		shown = [chunk for page_chunks in pages for chunk in page_chunks]

	context = {
		"header": get_report_header(filters.get("company")),
		"title": _("Grand Livre"),
		"du": from_date.strftime("%d/%m/%Y"),
		"au": to_date.strftime("%d/%m/%Y"),
		"layout": layout,
		"layout_label": _("Simple") if layout == "Simple" else _("Detaille"),
		"detaille": layout == "Detaille",
		"groups": shown,
		"page": current,
		"total_pages": total_pages,
		"fmt": _fmt,
	}
	return {
		"html": _render_template("ledger_data_page.html", context),
		"page": current,
		"total_pages": total_pages,
	}


def _fmt(value) -> str:
	"""Three decimals, system number format (French separators), minus sign."""
	return fmt_money(flt(value), precision=3, currency=REPORT_CURRENCY)


def _group_rows(rows: list[dict], from_date: date, to_date: date, year: int) -> list[dict]:
	"""Group the period's rows per account with a running balance; the group
	opens with the opening balance (movements from 01/01 of the year up to
	the day before from_date) and closes with a totals row."""
	accounts = []
	by_account: dict[str, list] = {}
	for row in rows:
		by_account.setdefault(row.account, []).append(row)
		if row.account not in accounts:
			accounts.append(row.account)

	if from_date > date(year, 1, 1):
		opening_until = from_date - timedelta(days=1)
	else:
		opening_until = None
	openings: dict[str, float] = {}
	if opening_until:
		for account in by_account:
			openings[account] = flt(
				frappe.db.get_value(
					LEDGER_DOCTYPE,
					[
						["account", "=", account],
						["posting_date", ">=", date(year, 1, 1)],
						["posting_date", "<=", opening_until],
					],
					"sum(debit) - sum(credit)",
				)
				or 0.0,
				3,
			)

	groups = []
	for account in accounts:
		display = (by_account[account][0].get("compte_comptable") or account)
		solde = openings.get(account, 0.0)
		movement_rows = []
		total_debit = total_credit = 0.0
		for row in by_account[account]:
			debit, credit = flt(row.debit), flt(row.credit)
			solde = flt(solde + debit - credit, 3)
			total_debit = flt(total_debit + debit, 3)
			total_credit = flt(total_credit + credit, 3)
			movement_rows.append(
				{
					"date": getdate(row.posting_date).strftime("%d/%m/%Y"),
					"mvt": row.mvt,
					"libelle": row.libelle,
					"jrn": row.journal,
					"ref": row.ref_doc,
					"tresorerie": row.tresorerie,
					"lettrage": row.lettrage,
					"debit": debit,
					"credit": credit,
					"solde": solde,
				}
			)
		groups.append(
			{
				"account": display,
				"opening": {
					"date": opening_until.strftime("%d/%m/%Y") if opening_until else from_date.strftime("%d/%m/%Y"),
					"solde": openings.get(account, 0.0),
				},
				"rows": movement_rows,
				"totals": {
					"debit": total_debit,
					"credit": total_credit,
					"solde": flt(openings.get(account, 0.0) + total_debit - total_credit, 3),
				},
				"row_count": len(movement_rows) + 2,
			}
		)
	return groups


def _paginate(groups: list[dict], rows_per_page: int) -> list[list[dict]]:
	"""Whole groups per page where possible; a group larger than a page is
	split at movement boundaries (the continuation reprints the column
	header but not the group header)."""
	pages: list[list[dict]] = []
	current: list[dict] = []
	used = 0
	for group in groups:
		if group["row_count"] > rows_per_page:
			# flush what is on the page, then split the big group
			if current:
				pages.append(current)
				current, used = [], 0
			remaining = list(group["rows"])
			first = True
			while remaining or (first and not group["rows"]):
				chunk_rows = remaining[: rows_per_page - 2]
				remaining = remaining[rows_per_page - 2 :]
				chunk = {
					"account": group["account"],
					"continued": not first,
					"opening": group["opening"] if first else None,
					"rows": chunk_rows if chunk_rows else [],
					"totals": group["totals"] if not remaining else None,
					"row_count": len(chunk_rows) + 2,
				}
				pages.append([chunk])
				first = False
			continue
		if used + group["row_count"] > rows_per_page and current:
			pages.append(current)
			current, used = [], 0
		current.append(group)
		used += group["row_count"]
	if current or not pages:
		pages.append(current)
	return [page for page in pages if page]


def _render_template(template_name: str, context: dict) -> str:
	path = os.path.join(os.path.dirname(__file__), template_name)
	with open(path, encoding="utf-8") as fh:
		source = fh.read()
	return frappe.get_jenv().from_string(source).render(context)
