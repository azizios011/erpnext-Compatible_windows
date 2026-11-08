# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class OperationTresorerie(Document):
	def validate(self):
		self.libelle = (self.libelle or "").strip()
		self.validate_unique()

	def validate_unique(self):
		existing = frappe.db.exists(
			"Operation Tresorerie",
			{
				"type_plan": self.type_plan,
				"categorie": self.categorie,
				"libelle": self.libelle,
				"name": ("!=", self.name or ""),
			},
		)
		if existing:
			frappe.throw(
				_("Une operation de tresorerie existe deja pour {0} / {1} avec ce libelle: {2}.").format(
					self.type_plan, self.categorie, existing
				)
			)


@frappe.whitelist()
def get_categorie_counts(type_plan: str = "Societe") -> dict:
	"""Live per-categorie counts for the list-view pill tabs."""
	_check_read()
	categories = frappe.get_all(
		"Operation Tresorerie",
		filters={"type_plan": type_plan},
		pluck="categorie",
	)
	counts: dict = {}
	for categorie in categories:
		counts[categorie] = counts.get(categorie, 0) + 1
	return {
		"Exploitation": counts.get("Exploitation", 0),
		"Investissement": counts.get("Investissement", 0),
		"Financement": counts.get("Financement", 0),
	}


def _check_read() -> None:
	if not frappe.has_permission("Operation Tresorerie", "read"):
		frappe.throw(_("Not permitted to read Operations de Tresorerie"), frappe.PermissionError)
