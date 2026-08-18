# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ReleveVente(Document):
	def on_trash(self):
		frappe.db.delete("Releve Vente Detail", {"releve_vente": self.name})
