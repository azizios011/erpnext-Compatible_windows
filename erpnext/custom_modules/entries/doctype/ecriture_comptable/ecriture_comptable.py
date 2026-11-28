# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext.custom_modules.entries.ledger_lock import (
	LEDGER_DOCTYPE,
	assert_row_not_declaration_locked,
)


class EcritureComptable(Document):
	def before_save(self):
		# belt and braces for direct doc edits: the posting and import paths
		# check the lock upstream (ledger_lock), this one catches a hand edit
		# of a stamped row in the desk
		if not (self.get("__islocal") or not self.name):
			assert_row_not_declaration_locked(self.name, action="modifier")

	def on_trash(self):
		if self.name and frappe.db.exists(LEDGER_DOCTYPE, self.name):
			assert_row_not_declaration_locked(self.name, action="supprimer")
