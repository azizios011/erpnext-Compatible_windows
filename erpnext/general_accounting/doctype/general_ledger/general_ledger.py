# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document

from erpnext.general_accounting.ledger import (
	fetch_entry_lines,
	get_period_dates,
	get_totals,
	lines_to_general_ledger_detail,
)


class GeneralLedger(Document):
	pass


@frappe.whitelist()
def get_entries(
	company,
	fiscal_year,
	period_type,
	month=None,
	from_date=None,
	to_date=None,
	account=None,
	journal_code=None,
	voucher_filter=None,
	ledger_type=None,
	extract_type=None,
):
	if not from_date or not to_date:
		from_date, to_date = get_period_dates(fiscal_year, period_type, month)

	if extract_type == "Compte sélectionné" and not account:
		frappe.throw(frappe._("Please select an account for the chosen extract type."))

	rows = fetch_entry_lines(
		company=company,
		from_date=from_date,
		to_date=to_date,
		account=account if extract_type == "Compte sélectionné" else None,
		journal_code=journal_code,
		voucher_filter=voucher_filter,
		ledger_type=ledger_type,
	)

	return {
		"from_date": from_date,
		"to_date": to_date,
		"entries": lines_to_general_ledger_detail(rows),
		**get_totals(rows),
	}
