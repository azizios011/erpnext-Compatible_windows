# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ModeleTaxe(Document):
	def validate(self):
		self.validate_default_per_sens()

	def validate_default_per_sens(self):
		"""Only one par_defaut model per sens (Achat / Vente / Achat et Vente)."""
		if not self.par_defaut:
			return
		existing = frappe.db.exists(
			"Modele Taxe",
			{
				"sens": self.sens,
				"par_defaut": 1,
				"name": ("!=", self.name or ""),
			},
		)
		if existing:
			frappe.throw(
				_("Un modele par defaut existe deja pour le sens {0}: {1}.").format(self.sens, existing)
			)
