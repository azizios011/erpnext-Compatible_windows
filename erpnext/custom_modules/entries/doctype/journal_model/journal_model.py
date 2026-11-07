# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from frappe import _


class JournalModel(Document):
	def validate(self):
		if not self.is_default:
			return
		existing = frappe.db.exists(
			"Journal Model",
			{"journal": self.journal, "is_default": 1, "name": ["!=", self.name or ""]},
		)
		if existing:
			frappe.throw(_("Journal {0} already has a default model: {1}.").format(self.journal, existing))
