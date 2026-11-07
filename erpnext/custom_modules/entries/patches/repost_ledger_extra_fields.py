# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

ENTRY_DOCTYPES = (
	"Payable Transaction",
	"Receivable Transaction",
	"Treasury Transaction",
	"Declaration Transaction",
)


def execute():
	"""Re-post every entry through the same posting function so existing
	Ecriture Comptable rows pick up the report fields (company, devise,
	ref_doc, tresorerie, mois, annee, lettrage).

	post_to_ledger is idempotent: it deletes the entry's rows and recreates
	them from the lines.
	"""
	for doctype in ENTRY_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		names = frappe.get_all(doctype, pluck="name")
		for name in names:
			doc = frappe.get_doc(doctype, name)
			doc.post_to_ledger()
		if names:
			frappe.logger("axeane").info(f"reposted {len(names)} {doctype} ledger rows")
