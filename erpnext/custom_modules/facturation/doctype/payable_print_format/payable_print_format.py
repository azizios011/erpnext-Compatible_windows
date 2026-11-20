# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class PayablePrintFormat(PrintFormatDocument):
	# Payable sidebar section: purchase-side documents; suppliers may hold
	# several layouts (achat category)
	CATEGORY = "achat"
	APPLIES_TO = ("Facture Achat", "RS Achat", "Releve Achat")
