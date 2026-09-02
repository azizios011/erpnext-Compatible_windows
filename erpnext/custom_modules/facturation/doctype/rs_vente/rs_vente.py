# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt


class RSVente(Document):
	def validate(self):
		self.calculate_amounts()

	def calculate_amounts(self):
		base = flt(self.taxable_base)
		rate = flt(self.withholding_rate)
		tva_retenue = flt(self.tva_retenue_source)

		self.amount_withheld = base * rate / 100

		self.montant_servi = base - self.amount_withheld - tva_retenue
