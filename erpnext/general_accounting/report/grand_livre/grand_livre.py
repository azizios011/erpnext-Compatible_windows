# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.general_accounting.ledger import fetch_entry_lines, get_period_dates


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_columns(filters):
	currency = filters.get("currency") or frappe.get_cached_value("Company", filters.company, "default_currency")
	return [
		{"fieldname": "movement_no", "label": _("Mvt"), "fieldtype": "Int", "width": 60},
		{"fieldname": "journal_code", "label": _("Jrn"), "fieldtype": "Data", "width": 70},
		{"fieldname": "account_display", "label": _("Compte Comptable"), "fieldtype": "Data", "width": 240},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "libelle", "label": _("Libellé"), "fieldtype": "Data", "width": 180},
		{"fieldname": "tresorerie", "label": _("Trésorerie"), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "debit",
			"label": _("Débit") + f" ({currency})",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"fieldname": "credit",
			"label": _("Crédit") + f" ({currency})",
			"fieldtype": "Currency",
			"width": 120,
		},
		{"fieldname": "lettering", "label": _("Lettrage"), "fieldtype": "Data", "width": 90},
		{"fieldname": "document_no", "label": _("N° Doc"), "fieldtype": "Data", "width": 120},
		{"fieldname": "voucher_no", "label": _("Voucher No"), "fieldtype": "Link", "options": "Entry of Entries", "width": 0, "hidden": 1},
	]


def get_data(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required"))

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	if not from_date or not to_date:
		from_date, to_date = get_period_dates(
			filters.get("fiscal_year"),
			filters.get("period_type"),
			filters.get("month"),
		)

	if filters.get("extract_type") == "Compte sélectionné" and not filters.get("account"):
		frappe.throw(_("Please select an account for the chosen extract type."))

	account = filters.get("account") if filters.get("extract_type") == "Compte sélectionné" else None

	rows = fetch_entry_lines(
		company=filters.company,
		from_date=from_date,
		to_date=to_date,
		account=account,
		journal_code=filters.get("journal_code"),
		voucher_filter=filters.get("voucher_filter"),
		ledger_type=filters.get("ledger_type"),
	)

	return [
		{
			"movement_no": row.movement_no,
			"journal_code": row.journal_code,
			"account_display": row.account_display,
			"posting_date": row.posting_date,
			"libelle": row.libelle or row.account_display,
			"tresorerie": row.tresorerie,
			"debit": flt(row.debit),
			"credit": flt(row.credit),
			"lettering": row.lettering,
			"document_no": row.document_no,
			"voucher_no": row.voucher_no,
		}
		for row in rows
	]
