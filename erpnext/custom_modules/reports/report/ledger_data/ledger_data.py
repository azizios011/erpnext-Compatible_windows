# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Ledger Data — Axeane's "Grand Livre" over the Ecriture Comptable ledger.

The LIST view is the native report page (filters, datatable, bottom
summary). The Grille builder (rows grouped per account with opening
balances and running totals) feeds the document views: the XLSX view embeds
the bundled GenOffice Sheets editor read-only on the generated workbook
(print_designer.api.ledger_documents), and the PDF view shows the PDF
converted from that same xlsx.
"""

from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import (
	AUX_CLIENT_PREFIX,
	AUX_FOURNISSEUR_PREFIX,
	BALANCE_TOLERANCE,
	REPORT_CURRENCY,
	as_list,
	check_ledger_read_permission,
	resolve_period,
)

LEDGER_DOCTYPE = "Ecriture Comptable"


def execute(filters=None) -> tuple:
	"""Standard Script Report entry point: columns, ONE PAGE of rows, no
	chart, and the report summary over ALL filtered rows (the totals stay
	global while the table pages). Every query is scoped to the dock
	context's Entreprise and Exercice."""
	filters = filters or {}
	context = require_context()
	if filters.get("view") == "Grille":
		columns = _get_grille_columns()
		rows = _get_grille_rows(filters, context)
		summary = _get_report_summary(_flat_rows(rows))
		rows, message = _paginate_grille(rows, filters)
		# the groups carry their own totals: no datatable total row
		# add_total_row is 0: the datatable never builds a total row anyway
		return columns, rows, message, None, summary
	columns = get_columns()
	rows = _get_rows(filters, context)
	summary = _get_report_summary(rows)
	rows, message = _paginate(rows, filters)
	_attach_documents(rows)
	return columns, rows, message, None, summary


def _paginate(rows: list[dict], filters: dict) -> tuple[list[dict], str]:
	"""Server-side paging for the list view: the client renders one page of
	rows; the summary above stays global over the whole filtered set."""
	total = len(rows)
	page_size = cint(filters.get("page_size")) or 20
	page = max(cint(filters.get("page")), 1)
	pages = max((total + page_size - 1) // page_size, 1)
	page = min(page, pages)
	start = (page - 1) * page_size
	page_rows = rows[start : start + page_size]
	if not total:
		return rows, ""
	message = _("Showing {0} - {1} of {2} rows (page {3} of {4}).").format(
		start + 1, start + len(page_rows), total, page, pages
	)
	return page_rows, message


def _paginate_grille(rows: list[dict], filters: dict) -> tuple[list[dict], str]:
	"""Server-side paging for the grille: account blocks are packed into
	pages of ~page_size rows (one account minimum per page — a single grille
	block can exceed the page size). The summary stays global."""
	# split the flat grille rows into per-account blocks on the header rows
	blocks: list[list[dict]] = []
	for row in rows:
		if row.get("row_type") == "header" or not blocks:
			blocks.append([row])
		else:
			blocks[-1].append(row)
	if not blocks:
		return rows, ""

	page_size = cint(filters.get("page_size")) or 20
	page = max(cint(filters.get("page")), 1)

	# pack the account blocks into pages bounded by the page size
	page_rows_list: list[list[dict]] = []
	current: list[dict] = []
	current_size = 0
	for block in blocks:
		if current and current_size + len(block) > page_size:
			page_rows_list.append(current)
			current = []
			current_size = 0
		current.extend(block)
		current_size += len(block)
	if current:
		page_rows_list.append(current)

	pages = len(page_rows_list)
	page = min(page, pages)
	out = page_rows_list[page - 1]
	accounts = sum(1 for row in out if row.get("row_type") == "header")
	message = _("Showing {0} of {1} accounts (page {2} of {3}).").format(accounts, len(blocks), page, pages)
	return out, message


def _account_filter(filters: dict, entreprise: str | None = None) -> list[str]:
	"""The Chart of Account rows selected by the grand-livre type."""
	ledger_type = filters.get("ledger_type") or "General"
	if ledger_type == "Auxiliaire Client":
		prefix = AUX_CLIENT_PREFIX
	elif ledger_type == "Auxiliaire Fournisseur":
		prefix = AUX_FOURNISSEUR_PREFIX
	else:
		return []
	cond: dict = {"account_number": ("like", f"{prefix}%")}
	if entreprise:
		cond["entreprise"] = entreprise
	return frappe.get_all(
		"Chart of Account",
		filters=cond,
		pluck="name",
	)


def _match_upper(acc_num: str, upper: str) -> bool:
	return acc_num <= upper or acc_num.startswith(upper)


def _match_lower(acc_num: str, lower: str) -> bool:
	return acc_num >= lower or acc_num.startswith(lower)


def _extract_account_filter(filters: dict, entreprise: str) -> list[str] | None:
	"""Resolve account filters from Type Extrait (Compte, Intervalle des comptes, Saisie libre).
	Returns None if unrestricted ('Tous les comptes', 'Comptes non soldes').
	Returns a list of Chart of Account names (which may be empty if no match)."""
	extract_type = filters.get("extract_type") or "Tous les comptes"
	if extract_type in ("Tous les comptes", "Comptes non soldes"):
		return None

	coas = frappe.get_all(
		"Chart of Account",
		filters={"entreprise": entreprise},
		fields=["name", "account_number", "account_name"],
	)

	if extract_type == "Compte":
		target = (filters.get("account") or "").strip()
		if not target:
			return []
		target_clean = target.split(" · ")[0].split(" - ")[0].strip()
		matched = []
		for acc in coas:
			num = acc.account_number or ""
			name = acc.name or ""
			if (
				target in (name, num)
				or (num and target_clean == num)
				or (num and target.startswith(f"{num} ·"))
				or (num and target.startswith(f"{num} -"))
			):
				matched.append(acc.name)
		return matched

	if extract_type == "Intervalle des comptes":
		from_raw = (filters.get("from_account") or "").strip()
		to_raw = (filters.get("to_account") or "").strip()
		if not from_raw and not to_raw:
			return []
		from_acc = from_raw.split(" - ")[0].split(" · ")[0].strip() if from_raw else ""
		to_acc = to_raw.split(" - ")[0].split(" · ")[0].strip() if to_raw else ""
		for acc in coas:
			if acc.name == from_raw and acc.account_number:
				from_acc = acc.account_number
			if acc.name == to_raw and acc.account_number:
				to_acc = acc.account_number
		matched = []
		for acc in coas:
			num = acc.account_number or ""
			if not num:
				continue
			if from_acc and not _match_lower(num, from_acc):
				continue
			if to_acc and not _match_upper(num, to_acc):
				continue
			matched.append(acc.name)
		return matched

	if extract_type == "Saisie libre":
		raw = (filters.get("saisie_libre") or "").strip()
		if not raw:
			return []
		tokens = [t.strip() for t in raw.split(",") if t.strip()]
		if not tokens:
			return []
		matched = []
		for acc in coas:
			num = acc.account_number or ""
			if not num:
				continue
			match_token = False
			for token in tokens:
				if "-" in token:
					parts = [p.strip() for p in token.split("-", 1)]
					lower, upper = parts[0], parts[1] if len(parts) > 1 else ""
					if (not lower or _match_lower(num, lower)) and (not upper or _match_upper(num, upper)):
						match_token = True
						break
				else:
					if num.startswith(token) or num == token:
						match_token = True
						break
			if match_token:
				matched.append(acc.name)
		return matched

	return None


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

	ledger_type = filters.get("ledger_type") or "General"
	ledger_accounts = _account_filter(filters, context["entreprise"]) if ledger_type != "General" else None
	extract_accounts = _extract_account_filter(filters, context["entreprise"])

	if ledger_accounts is not None and extract_accounts is not None:
		intersected = sorted(list(set(ledger_accounts) & set(extract_accounts)))
		if intersected:
			out.append(["account", "in", intersected])
		else:
			out.append(["name", "=", ""])
	elif ledger_accounts is not None:
		if ledger_accounts:
			out.append(["account", "in", ledger_accounts])
		else:
			out.append(["name", "=", ""])
	elif extract_accounts is not None:
		if extract_accounts:
			out.append(["account", "in", extract_accounts])
		else:
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
	# "Tous les comptes" shows the period's rows; account filtering is done in _ledger_filters

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
		# narrow action-icon column (document / eye / pen), no header label
		{"fieldname": "actions", "fieldtype": "Data", "width": 120},
	]


def _attach_documents(rows: list[dict]) -> None:
	"""Set has_document / document_file (attachment url) / document_file_name
	(File docname, for the read-only pdf-editor page) on the CURRENT page's
	rows. ONE query per source_doctype group — never per row."""
	by_doctype: dict[str, list[str]] = {}
	for row in rows:
		if row.get("source_doctype") and row.get("source_name"):
			by_doctype.setdefault(row["source_doctype"], []).append(row["source_name"])

	files: dict[tuple[str, str], dict] = {}
	for doctype, names in by_doctype.items():
		for file_row in frappe.get_all(
			"File",
			filters={"attached_to_doctype": doctype, "attached_to_name": ("in", names)},
			fields=["name", "attached_to_name", "file_url"],
			order_by="creation desc",
		):
			key = (doctype, file_row.attached_to_name)
			files.setdefault(key, file_row)  # the latest attachment wins

	for row in rows:
		file_row = files.get((row.get("source_doctype") or "", row.get("source_name") or ""))
		row["has_document"] = 1 if file_row else 0
		row["document_file"] = file_row.file_url if file_row else ""
		row["document_file_name"] = file_row.name if file_row else ""


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

	from_date, _to_date = resolve_period(filters, context)

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
		out.append({"row_type": "header", "date": display, "account": account})
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
					"account": account,
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
					"source_entry": row.source_entry,
					"source_doctype": row.source_doctype,
					"source_name": row.source_name,
				}
			)
		out.append(
			{
				"row_type": "total",
				"account": account,
				"date": _("Totaux {0}").format(display),
				"debit": total_debit,
				"credit": total_credit,
				"solde": flt(openings.get(account, 0.0) + total_debit - total_credit, 3),
			}
		)
	return out
