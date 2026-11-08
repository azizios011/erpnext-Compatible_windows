# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import re
from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime

MATRICULE_FISCAL_PATTERN = re.compile(r"^\d{7}[A-Z]{3}\d{3}$")


class Entreprise(Document):
	def validate(self):
		self.normalize_code()
		self.normalize_matricule_fiscal()
		self.validate_jour_arrete()
		self.default_type_plan_comptable()
		self.update_users_summary()
		self.stamp_plan_comptable()

	def normalize_code(self):
		if self.code:
			self.code = self.code.strip().upper()

	def normalize_matricule_fiscal(self):
		if not self.matricule_fiscal:
			return
		normalized = re.sub(r"[\s/-]+", "", self.matricule_fiscal).upper()
		if not MATRICULE_FISCAL_PATTERN.match(normalized):
			frappe.throw(
				_("Le matricule fiscal doit respecter le format tunisien: 7 chiffres, 3 lettres, 3 chiffres (ex: 1234567ABC001).")
			)
		self.matricule_fiscal = normalized

	def validate_jour_arrete(self):
		mois = cint(self.mois_arrete) or 12
		jour = cint(self.jour_arrete) or 31
		while True:
			try:
				date(2024, mois, jour)  # leap year: 29 is valid for 02
				break
			except ValueError:
				jour -= 1
		if jour != cint(self.jour_arrete):
			frappe.throw(
				_("Le jour d'arrete {0} n'est pas valide pour le mois {1} (31 pour 12 est admis, 31 pour 04 refuse).").format(
					cint(self.jour_arrete), mois
				)
			)
		self.jour_arrete = jour

	def default_type_plan_comptable(self):
		if self.personne_physique and not self.type_plan_comptable:
			self.type_plan_comptable = "Personne Physique"

	def update_users_summary(self):
		"""The list view shows the assigned users; keep the JSON blob and the
		count in sync with assigned_staff."""
		users = [row.user for row in (self.assigned_staff or []) if row.user]
		self.utilisateurs_json = json.dumps(users)
		self.nb_utilisateurs = len(users)

	def stamp_plan_comptable(self):
		if self.has_value_changed("plan_comptable_fichier"):
			self.plan_comptable_ajoute_le = now_datetime() if self.plan_comptable_fichier else None

	def after_insert(self):
		"""Create the current year's Exercice when the Entreprise has none
		(idempotent: skipped when one already covers the year)."""
		annee = date.today().year
		exists = frappe.db.exists("Exercice", {"entreprise": self.name, "annee": annee})
		if exists:
			return
		try:
			from erpnext.custom_modules.organization.doctype.exercice.exercice import default_dates

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


@frappe.whitelist()
def valider_entreprise(name: str) -> str:
	"""Set the Entreprise to Creee: re-runs the full validation, refuses when
	a mandatory field is still empty, then saves."""
	doc = frappe.get_doc("Entreprise", name)
	doc.check_permission("write")

	doc.run_method("validate")

	missing = [df.label or df.fieldname for df in doc.get_missing_mandatory_fields()]
	if missing:
		frappe.throw(
			_("Impossible de valider: champs obligatoires vides: {0}.").format(", ".join(missing))
		)

	doc.status = "Creee"
	doc.save()
	return doc.status
