import frappe

REMOVED_DOCTYPES = (
	"Customer Ledger",
	"Customer Ledger Detail",
	"Supplier Ledger",
	"Supplier Ledger Detail",
)


def execute():
	for doctype in REMOVED_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)

	for label in ("Customer Ledger", "Supplier Ledger"):
		for shortcut in frappe.get_all(
			"Workspace Shortcut",
			filters={"parent": "States", "label": label},
			pluck="name",
		):
			frappe.delete_doc("Workspace Shortcut", shortcut, ignore_permissions=True, force=True)

	frappe.db.commit()
