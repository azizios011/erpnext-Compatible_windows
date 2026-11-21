# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class ReceivablePrintFormat(PrintFormatDocument):
	# Receivable sidebar section; the engine category (vente) is kept as
	# plain Python for the later template-engine stage, not as a field
	CATEGORY = "vente"
	SINGLE_LAYOUT = True
	CATEGORY_OPTIONS = ("Facture Vente", "RS Vente", "Releve Vente")
	OWNER_FIELDS = ("client",)
	PARTY_FIELD = "client"
	RELEVE_CATEGORY = "Releve Vente"
	RELEVE_TABLE = "releve_clients"
	RELEVE_CHILD_DOCTYPE = "Receivable Print Format Client"
	RELEVE_CHILD_FIELD = "client"
