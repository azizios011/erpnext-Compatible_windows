# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class TreasuryPrintFormat(PrintFormatDocument):
	# Treasury sidebar section: bank documents; bank accounts may hold
	# several layouts (bank category)
	CATEGORY = "bank"
	APPLIES_TO = ("Releve Bancaire", "Remise de Cheque", "Versement Espece")
