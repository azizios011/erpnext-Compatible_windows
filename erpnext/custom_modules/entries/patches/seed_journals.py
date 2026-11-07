# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

# The five journals of the Entries workspace; the code is the Journal
# docname and the numbering-series prefix shared with Facturation.
SEEDS = [
	{"journal_code": "AC", "journal_name": "Achats", "journal_type": "Achat"},
	{"journal_code": "VT", "journal_name": "Ventes", "journal_type": "Vente"},
	{"journal_code": "BQ", "journal_name": "Banque", "journal_type": "Banque"},
	{"journal_code": "RS", "journal_name": "Retenues source", "journal_type": "Retenue"},
	{"journal_code": "DC", "journal_name": "Declarations", "journal_type": "Declaration"},
]


def execute():
	for seed in SEEDS:
		if frappe.db.exists("Journal", seed["journal_code"]):
			continue
		frappe.get_doc({"doctype": "Journal", **seed}).insert(ignore_permissions=True)
