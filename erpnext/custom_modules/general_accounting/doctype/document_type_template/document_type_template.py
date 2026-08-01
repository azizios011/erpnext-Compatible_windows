# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DocumentTypeTemplate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		document_type_category: DF.Autocomplete
		meaning: DF.Literal["", "Debtor", "Creditor", "Debtor or Creditor"]
		template_title: DF.Data
	# end: auto-generated types

	pass


@frappe.whitelist()
def get_document_type_categories(txt=None, **kwargs):
	from erpnext.custom_modules.general_accounting.doctype.document_type_template.facturation import (
		CATEGORIES,
	)

	txt = (txt or "").lower()
	return [
		{"value": folder_name, "label": label}
		for folder_name, label in CATEGORIES.items()
		if txt in label.lower() or txt in folder_name.lower()
	]
