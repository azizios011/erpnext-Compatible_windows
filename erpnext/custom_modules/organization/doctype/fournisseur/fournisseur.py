# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from erpnext.custom_modules.organization.tiers_accounts import validate_tiers_account


class Fournisseur(Document):
	def validate(self):
		# a Fournisseur can only live on a custom account under 401 (see
		# organization/tiers_accounts.py for the shared rules)
		validate_tiers_account(self)
