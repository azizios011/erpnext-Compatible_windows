# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils import money_in_words


class FactureVente(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		total_ht = 0.0
		for row in self.items:
			row.amount = flt(row.qty) * flt(row.rate)
			total_ht += flt(row.amount)

		total_taxes = 0.0
		for tax in self.taxes:
			total_taxes += flt(tax.tax_amount)

		self.total_ht = total_ht
		self.total_taxes_and_charges = total_taxes
		self.grand_total = total_ht + total_taxes

		if self.grand_total and self.company:
			company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
			self.in_words = money_in_words(self.grand_total, company_currency)
