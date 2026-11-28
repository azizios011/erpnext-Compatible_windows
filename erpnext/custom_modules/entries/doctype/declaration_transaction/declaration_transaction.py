# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Declaration Transaction — the ledger-driven Déclaration Mensuelle.

Deliberately NOT an EntryDocument: the DM no longer posts journal lines, it
is computed from the Ecriture Comptable ledger by
erpnext.custom_modules.entries.declaration_engine and lives through the
Brouillon -> Cloture -> Depose workflow (whitelisted POST methods). A manual
save may only reach a Brouillon, and only its carry changes meaning (first
declaration of an exercice): everything else is recomputed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from erpnext.custom_modules.entries.declaration_engine import (
	STATUS_BROUILLON,
	_previous_principale,
	compute_totals,
	render_totaux_html,
)
from erpnext.custom_modules.organization.context import require_context

LINE_KEYS = ("code", "retenu")


class DeclarationTransaction(Document):
	def before_insert(self):
		# the context is the only source: the user never picks a company
		context = require_context()
		self.entreprise = context["entreprise"]
		self.exercice = context["exercice"]
		if not self.status:
			self.status = STATUS_BROUILLON

	def validate(self):
		self.validate_editable()
		self.validate_period()
		self.validate_rubriques()
		self.validate_carry()
		self.recompute_from_lines()

	def validate_editable(self):
		"""The workflow drives the status: a manual save only reaches a
		Brouillon (compute, cloture, depose write through db.set_value)."""
		if self.get("__islocal") or not self.name:
			if self.status != STATUS_BROUILLON:
				self.status = STATUS_BROUILLON
			return
		previous_status = frappe.db.get_value(self.doctype, self.name, "status")
		if previous_status and previous_status != STATUS_BROUILLON:
			frappe.throw(
				_("La declaration {0} est {1}: seule une Brouillon peut etre modifiee.").format(
					self.name, previous_status
				)
			)

	def validate_period(self):
		mois = int(str(self.mois or 0))
		if not 1 <= mois <= 12:
			frappe.throw(_("Le mois de la declaration doit valoir 01 - 12."))
		annee = frappe.db.get_value("Exercice", self.exercice, "annee")
		if not annee:
			frappe.throw(_("L'exercice {0} n'a pas d'annee.").format(self.exercice))
		self.annee = annee

	def validate_rubriques(self):
		if not self.rubriques:
			frappe.throw(
				_("La declaration se calcule depuis le grand livre: utilisez le bouton Calculer.")
			)

	def validate_carry(self):
		"""report_credit_anterieur is editable on the FIRST declaration of the
		exercice only; afterwards the previous Principale imposes it
		(negative = credit)."""
		previous = _previous_principale(self.entreprise, self.exercice, int(self.mois))
		if not previous:
			return
		expected = -flt(previous.credit_suivant, 3)
		if flt(self.report_credit_anterieur, 3) != expected:
			frappe.throw(
				_("Le credit reporte anterieur est impose par la declaration precedente: {0}.").format(
					frappe.bold(f"{expected:,.3f}")
				)
			)

	def recompute_from_lines(self):
		"""The totals derive from the frozen rubrique lines + the carry, so a
		carry edit on a first declaration keeps the TVA position consistent."""
		lines = [{key: line.get(key) for key in LINE_KEYS} for line in self.rubriques]
		totals = compute_totals(lines, self.report_credit_anterieur)
		for key, value in totals.items():
			setattr(self, key, flt(value, 3))
		self.totaux_html = render_totaux_html(totals)
