# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Ledger rows created before the lettrage_status field default it to
	empty; stamp them Non lettre (lettrage backfill covers lettered rows:
	none can exist before this stage)."""
	if not frappe.db.exists("DocType", "Ecriture Comptable"):
		return
	names = frappe.get_all(
		"Ecriture Comptable",
		filters={"lettrage_status": ("is", "not set")},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value(
			"Ecriture Comptable", name, "lettrage_status", "Non lettre", update_modified=False
		)
	if names:
		frappe.logger("axeane").info(f"lettrage_status backfilled on {len(names)} ledger rows")
