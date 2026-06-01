# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.model.document import Document

from erpnext.tunisian_accounting.ledger import (
	fetch_entry_lines,
	lines_to_party_ledger_detail,
	with_running_balance,
)


class SupplierLedger(Document):
	pass


@frappe.whitelist()
def get_entries(company, from_date, to_date, supplier=None):
	rows = fetch_entry_lines(
		company,
		from_date,
		to_date,
		party_type="Supplier",
		party=supplier,
	)
	return lines_to_party_ledger_detail(with_running_balance(rows))
