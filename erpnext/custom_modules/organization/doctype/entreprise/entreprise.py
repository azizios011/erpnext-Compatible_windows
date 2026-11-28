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
	def before_insert(self):
		# autoname field:code takes the name from the RAW client value before
		# validate runs (and _sync_autoname_field later resets the field to the
		# name): normalize first, so name == code == the upper-cased code
		self.normalize_code()

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
		raw_mois = cint(self.mois_arrete)
		raw_jour = cint(self.jour_arrete)
		# empty means the defaults (31/12): the island form fills them from the
		# meta defaults, but a partial payload or a legacy row must not be
		# rejected over an unset jour — only a TYPED jour the month cannot
		# hold throws. mois stays inside 1..12 and jour inside 1..31 before the
		# clamp loop, or date() would fail forever and hang the save.
		mois = raw_mois if 1 <= raw_mois <= 12 else 12
		jour = raw_jour or 31
		if not 1 <= jour <= 31:
			frappe.throw(_("Le jour d'arrete {0} n'est pas valide (1 - 31).").format(raw_jour))
		while True:
			try:
				date(2024, mois, jour)  # leap year: 29 is valid for 02
				break
			except ValueError:
				jour -= 1
		if raw_jour and jour != raw_jour:
			frappe.throw(
				_("Le jour d'arrete {0} n'est pas valide pour le mois {1} (31 pour 12 est admis, 31 pour 04 refuse).").format(
					raw_jour, mois
				)
			)
		self.mois_arrete = mois
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
def save_entreprise(doc: dict) -> dict:
	"""Full-document save from the Entreprise island page: update the loaded
	doc with the client's fields (child tables included — assigning a fresh
	list replaces it, so rows removed on the island are deleted here) and run
	the normal validate + save pipeline."""
	if isinstance(doc, str):
		doc = json.loads(doc)
	name = (doc or {}).get("name")
	if not name:
		frappe.throw(_("name is required"))

	loaded = frappe.get_doc("Entreprise", name)
	loaded.check_permission("write")
	loaded.update(doc)
	loaded.save()
	return loaded.as_dict()


@frappe.whitelist()
def valider_entreprise(name: str) -> str:
	"""Set the Entreprise to Creee: re-runs the full validation, refuses when
	a mandatory field is still empty, then saves."""
	doc = frappe.get_doc("Entreprise", name)
	doc.check_permission("write")

	doc.run_method("validate")

	# the fork's mandatory collector: (fieldname, message) tuples, parent and
	# child rows alike
	missing = doc._get_missing_mandatory_fields() + [
		row for child in doc.get_all_children() for row in child._get_missing_mandatory_fields()
	]
	if missing:
		labels = []
		for fieldname, _message in missing:
			df = doc.meta.get_field(fieldname)
			label = (df.label if df else None) or fieldname
			if label not in labels:
				labels.append(label)
		frappe.throw(
			_("Impossible de valider: champs obligatoires vides: {0}.").format(", ".join(labels))
		)

	doc.status = "Creee"
	doc.save()
	return doc.status
