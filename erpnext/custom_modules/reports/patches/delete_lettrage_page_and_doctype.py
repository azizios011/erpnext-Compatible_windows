# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Lettrage became a Script Report (report/lettrage). The old Page and the
	Single "Lettrage" doctype shared the /app/lettrage slug — frappe's router
	resolved the doctype first and the sidebar opened an empty form. Remove
	both stale records; idempotent via ignore_missing (the migrate's orphan
	reaper would also drop them, this just does not wait for it)."""
	frappe.delete_doc("DocType", "Lettrage", force=1, ignore_missing=True)
	frappe.delete_doc("Page", "lettrage", force=1, ignore_missing=True)
	frappe.clear_cache()
