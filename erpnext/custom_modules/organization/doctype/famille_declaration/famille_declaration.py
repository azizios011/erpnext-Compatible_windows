# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from erpnext.custom_modules.organization.context import require_context


class FamilleDeclaration(Document):
	def validate(self):
		if not 1 <= cint(self.code) <= 11:
			frappe.throw(_("Le code famille doit etre compris entre 1 et 11."))
		self.famille_code = (self.famille_code or "").strip()
		if not self.famille_code:
			frappe.throw(_("Le code famille (famille_code) est obligatoire."))
		if not cint(self.inclus) and not (self.exclusion_reason or "").strip():
			frappe.throw(_("Le motif d'exclusion est obligatoire quand la famille n'est pas incluse."))

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
