# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class ReceivablePrintFormat(PrintFormatDocument):
	# Receivable sidebar section: sales-side documents; one layout per
	# company (vente: layout_id "default" only)
	CATEGORY = "vente"
	APPLIES_TO = ("Facture Vente", "RS Vente", "Releve Vente")
