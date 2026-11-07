# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

from erpnext.custom_modules.facturation.facturation_base import FacturationDocument


class ReleveVente(FacturationDocument):
	journal_code = "VT"

	def on_trash(self):
		frappe.db.delete("Releve Vente Detail", {"releve_vente": self.name})
