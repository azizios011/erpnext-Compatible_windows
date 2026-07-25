# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class DocumentTypeTemplate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from erpnext.custom_modules.general_accounting.doctype.document_type_template_amount.document_type_template_amount import (
			DocumentTypeTemplateAmount,
		)

		amount_breakdown: DF.Table[DocumentTypeTemplateAmount]
		bulk_column_config: DF.Code | None
		company: DF.Link
		entry_mode: DF.Literal["Single", "Bulk"]
		meaning: DF.Literal["", "Debtor", "Creditor", "Debtor or Creditor"]
		template_title: DF.Data
	# end: auto-generated types

	def validate(self):
		self.validate_party()
		self.validate_account_company()

	def validate_account_company(self):
		"""Each row's account must belong to the template's company."""
		for account in self.amount_breakdown:
			if (
				account.account
				and frappe.get_cached_value("Account", account.account, "company") != self.company
			):
				frappe.throw(
					_("Row {0}: Account {1} does not belong to company {2}").format(
						account.idx, account.account, self.company
					)
				)

	def validate_party(self):
		"""
		Loop over all accounts and see if party and party type is set correctly
		"""
		for account in self.amount_breakdown:
			if account.party_type:
				account_type = frappe.get_cached_value("Account", account.account, "account_type")
				if account_type not in ["Receivable", "Payable"]:
					frappe.throw(
						_(
							"Check row {0} for account {1}: Party Type is only allowed for Receivable or Payable accounts"
						).format(account.idx, account.account)
					)

			if account.party and not account.party_type:
				frappe.throw(
					_("Check row {0} for account {1}: Party is only allowed if Party Type is set").format(
						account.idx, account.account
					)
				)
