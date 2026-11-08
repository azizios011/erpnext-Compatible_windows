# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from erpnext.custom_modules.organization.doctype.exercice.exercice import default_dates


class Entreprise(Document):
	def after_insert(self):
		"""Create the current year's Exercice when the Entreprise has none
		(idempotent: skipped when one already covers the year)."""
		from datetime import date

		annee = date.today().year
		exists = frappe.db.exists(
			"Exercice", {"entreprise": self.name, "annee": annee}
		)
		if exists:
			return
		try:
			date_debut, date_fin = default_dates(self.name, annee)
			frappe.get_doc(
				{
					"doctype": "Exercice",
					"entreprise": self.name,
					"annee": annee,
					"date_debut": date_debut,
					"date_fin": date_fin,
					"status": "Ouvert",
				}
			).insert(ignore_permissions=True)
		except Exception:
			# the Entreprise insert must not fail over its exercice
			frappe.log_error("axeane exercice creation failed", frappe.get_traceback())
