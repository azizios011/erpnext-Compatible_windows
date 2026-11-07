# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Virement Espece was a misnomer: it records cash deposits.

	Rename the DocType to Versement Espece on sites that already carry the
	old one. Guards follow rename_sales_taxes_template in
	custom_modules/setup.py: check the DocType record (not the table — the
	orphan cleanup can leave one behind), and merge when a migrate has
	already created the new doctype from its JSON.
	"""
	old, new = "Virement Espece", "Versement Espece"
	if not frappe.db.exists("DocType", old):
		# fresh site (only Versement Espece was ever synced) or already renamed
		return
	if not frappe.db.exists("DocType", new):
		frappe.rename_doc("DocType", old, new, force=True)
	else:
		# the migrate sync created the new doctype before this patch ran:
		# merge moves the rows across and repoints every stored Link
		frappe.rename_doc("DocType", old, new, merge=True, force=True)
	# the top-level frappe.rename_doc wrapper takes no ignore_permissions in
	# this frappe version; reload so the renamed meta is fresh
	frappe.reload_doctype(new, force=True)
