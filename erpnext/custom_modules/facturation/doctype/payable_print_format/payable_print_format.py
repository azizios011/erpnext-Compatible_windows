# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class PayablePrintFormat(PrintFormatDocument):
	# Payable sidebar section; the engine category (achat) is kept as plain
	# Python for the later template-engine stage, not as a field
	CATEGORY = "achat"
	CATEGORY_OPTIONS = ("Facture Achat", "RS Achat", "Releve Achat")
	OWNER_FIELDS = ("supplier",)
	PARTY_FIELD = "supplier"
	RELEVE_CATEGORY = "Releve Achat"
	RELEVE_TABLE = "releve_suppliers"
	RELEVE_CHILD_DOCTYPE = "Payable Print Format Supplier"
	RELEVE_CHILD_FIELD = "supplier"
