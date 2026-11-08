# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

CARDS = (
	"Total Payable Entries",
	"Total Receivable Entries",
	"Total Treasury Entries",
	"Total Declaration Entries",
)


def execute():
	"""The four entry cards became the Totaux section (form + list); remove
	their Number Card records and any stale workspace references."""
	for label in CARDS:
		if not frappe.db.exists("Number Card", label):
			continue
		frappe.delete_doc("Number Card", label, force=True, ignore_missing=True)

	if frappe.db.exists("Workspace", "Entries"):
		ws = frappe.get_doc("Workspace", "Entries")
		remaining = [row for row in (ws.number_cards or []) if row.number_card_name not in CARDS]
		if len(remaining) != len(ws.number_cards or []):
			ws.number_cards = remaining
			ws.save(ignore_permissions=True)
