# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""The Operation Tresorerie Compte child doctype was retired together with
	the "Comptes associes" column of Operation Tresorerie."""
	frappe.delete_doc("DocType", "Operation Tresorerie Compte", force=True, ignore_missing=True)
