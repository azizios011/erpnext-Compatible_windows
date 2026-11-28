# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext.custom_modules.organization.context import require_context

RUBRIQUE_CODE_PATTERN = re.compile(r"^F\d{1,2}(_\d{1,3}){0,3}$")


class RubriqueDeclaration(Document):
	def validate(self):
		self.code = (self.code or "").strip().upper()
		if not RUBRIQUE_CODE_PATTERN.match(self.code):
			frappe.throw(_("Le code rubrique suit le modele F1_1 / F5_2_4 / F9_3_1."))
		self.validate_calcul()

	def validate_calcul(self):
		"""COMPTE sides need a sens and at least one account interval; the
		derived and fixed types need no accounts and no sens."""
		for label, calc_type, sens_field, comptes_field in (
			("brut", self.type_calcul_brut, "sens_brut", "comptes_brut"),
			("retenu", self.type_calcul_retenu, "sens_retenu", "comptes_retenu"),
		):
			comptes = self.get(comptes_field) or []
			if calc_type == "COMPTE":
				if not self.get(sens_field):
					frappe.throw(_("Le sens du montant {0} est obligatoire en calcul COMPTE.").format(_(label)))
				if not comptes:
					frappe.throw(_("Au moins un compte est obligatoire pour le montant {0} en calcul COMPTE.").format(_(label)))
			else:
				if comptes:
					frappe.throw(
						_("Les comptes du montant {0} ne s'appliquent qu'au calcul COMPTE.").format(_(label))
					)
			for row in comptes:
				if row.compte_a and row.compte_a == row.compte_de:
					frappe.throw(
						_("Ligne {0}: la borne haute doit differer de la borne basse (vide = prefixe).").format(row.idx)
					)
				for account in (row.compte_de, row.compte_a):
					if account and not frappe.db.exists(
						"Chart of Account", {"name": account, "entreprise": self.entreprise}
					):
						frappe.throw(
							_("Ligne {0}: le compte {1} n'appartient pas au plan comptable de l'entreprise.").format(
								row.idx, frappe.bold(account)
							)
						)

	def before_insert(self):
		# the context is the only source: the user never picks a company
		context = require_context()
		if self.entreprise and self.entreprise != context["entreprise"]:
			frappe.throw(
				_("L'entreprise {0} n'est pas celle du contexte comptable ({1}).").format(
					self.entreprise, context["entreprise"]
				)
			)
		self.entreprise = context["entreprise"]
