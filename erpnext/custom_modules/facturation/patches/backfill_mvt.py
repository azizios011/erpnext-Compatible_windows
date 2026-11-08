# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

from erpnext.custom_modules.facturation.facturation_base import JOURNAL_BY_DOCTYPE


def execute():
	"""Backfill the read-only MVT/Journal fields on records created before
	they existed: mvt is the document's own (series) name, journal is the
	doctype's code. frappe.db.set_value fires no hooks and leaves modified
	untouched, so lists and linked views keep their order."""
	for doctype, journal_code in JOURNAL_BY_DOCTYPE.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		names = frappe.get_all(doctype, filters={"mvt": ("is", "not set")}, pluck="name")
		for name in names:
			frappe.db.set_value(
				doctype,
				name,
				{"mvt": name, "journal": journal_code},
				update_modified=False,
			)
		# records imported with an mvt but no journal still get the code
		names = frappe.get_all(
			doctype,
			filters={"journal": ("is", "not set")},
			pluck="name",
		)
		for name in names:
			frappe.db.set_value(doctype, name, "journal", journal_code, update_modified=False)
		if names:
			frappe.logger("axeane").info(f"backfilled mvt/journal on {doctype}")
