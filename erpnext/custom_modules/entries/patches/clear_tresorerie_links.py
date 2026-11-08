# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""The tresorerie fields used to hold Chart of Account names; they now
	hold Operation Tresorerie names. Clear every stale value (values that
	are not existing Operation Tresorerie names), keeping genuinely valid
	ones untouched."""
	if not frappe.db.exists("DocType", "Operation Tresorerie"):
		frappe.logger("axeane").info("Operation Tresorerie missing; nothing to clear")
		return

	valid = set(frappe.get_all("Operation Tresorerie", pluck="name"))
	cleared = 0

	for doctype in ("Ecriture Ligne", "Ecriture Comptable"):
		if not frappe.db.exists("DocType", doctype):
			continue
		names = frappe.get_all(doctype, filters={"tresorerie": ("is", "set")}, fields=["name", "tresorerie"])
		stale = [row for row in names if row.tresorerie not in valid]
		for row in stale:
			frappe.db.set_value(doctype, row.name, "tresorerie", "", update_modified=False)
		cleared += len(stale)
		if stale:
			frappe.logger("axeane").info(f"cleared {len(stale)} stale tresorerie values on {doctype}")

	frappe.logger("axeane").info(f"tresorerie links cleared: {cleared} row(s) total")
