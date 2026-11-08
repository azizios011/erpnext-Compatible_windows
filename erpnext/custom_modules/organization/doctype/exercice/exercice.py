# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from datetime import date, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate


class Exercice(Document):
	def validate(self):
		self.validate_dates()
		self.validate_overlap()
		self.validate_unique_pair()
		self.libelle = f"EX {cint(self.annee)}"

	def validate_dates(self):
		debut = getdate(self.date_debut)
		fin = getdate(self.date_fin)
		if fin <= debut:
			frappe.throw(_("La date de fin doit etre posterieure a la date de debut."))
		length_months = (fin.year - debut.year) * 12 + (fin.month - debut.month)
		if length_months > 24:
			frappe.throw(_("L'exercice ne peut pas durer plus de 24 mois."))

	def validate_overlap(self):
		overlap = frappe.db.exists(
			"Exercice",
			{
				"entreprise": self.entreprise,
				"name": ("!=", self.name or ""),
				"date_debut": ("<=", getdate(self.date_fin)),
				"date_fin": (">=", getdate(self.date_debut)),
			},
		)
		if overlap:
			frappe.throw(
				_("Chevauchement avec l'exercice {0} ({1} - {2}).").format(
					overlap,
					frappe.db.get_value("Exercice", overlap, "date_debut"),
					frappe.db.get_value("Exercice", overlap, "date_fin"),
				)
			)

	def validate_unique_pair(self):
		existing = frappe.db.exists(
			"Exercice",
			{"entreprise": self.entreprise, "annee": self.annee, "name": ("!=", self.name or "")},
		)
		if existing:
			frappe.throw(
				_("Un exercice existe deja pour {0} - {1}: {2}.").format(
					self.entreprise, cint(self.annee), existing
				)
			)

	def on_trash(self):
		if self.status == "Cloture":
			frappe.throw(_("Un exercice cloture ne peut pas etre supprime."))


def _minus_months(day: date, months: int) -> date:
	year = day.year
	month = day.month - months
	while month <= 0:
		month += 12
		year -= 1
	day_number = day.day
	while True:
		try:
			return date(year, month, day_number)
		except ValueError:
			day_number -= 1  # clamp to the month length (31 -> 30 -> 29 -> 28)


def default_dates(entreprise: str, annee: int) -> tuple[date, date]:
	"""Defaults from the Entreprise: date_fin = (annee, mois_arrete,
	jour_arrete) clamped to the month length; date_debut = date_fin minus
	duree_exercice months plus one day."""
	mois = cint(frappe.db.get_value("Entreprise", entreprise, "mois_arrete")) or 12
	jour = cint(frappe.db.get_value("Entreprise", entreprise, "jour_arrete")) or 31
	duree = cint(frappe.db.get_value("Entreprise", entreprise, "duree_exercice")) or 12

	while True:
		try:
			date_fin = date(annee, mois, jour)
			break
		except ValueError:
			jour -= 1  # clamp to the month length (31 -> 30 -> 29 -> 28)

	date_debut = _minus_months(date_fin, duree) + timedelta(days=1)
	return date_debut, date_fin
