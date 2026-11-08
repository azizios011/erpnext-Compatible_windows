# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from frappe.model.document import Document

# 8-hour workdays: change here if the convention basis moves
HEURES_PAR_JOUR = 8


class ConventionCollective(Document):
	def validate(self):
		self.validate_non_negative()
		# computed, never typed
		self.nombre_heures = flt(self.nombre_jours) * HEURES_PAR_JOUR

	def validate_non_negative(self):
		for fieldname, label in (
			("nombre_jours", _("Nombre de jours")),
			("nombre_heures", _("Nombre d'heures")),
			("droit_conge", _("Droit au conge")),
		):
			if flt(self.get(fieldname)) < 0:
				frappe.throw(_("{0} ne peut pas etre negatif.").format(label))
