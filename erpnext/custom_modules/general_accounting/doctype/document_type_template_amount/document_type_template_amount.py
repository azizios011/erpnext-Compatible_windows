# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class DocumentTypeTemplateAmount(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		component: DF.Literal["TTC", "TVA", "HT TVA", "Timbre"]
		credit: DF.Check
		debit: DF.Check
		montant: DF.Currency
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		rate: DF.Percent
	# end: auto-generated types

	pass
