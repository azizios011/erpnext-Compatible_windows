# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class TreasuryPrintFormat(PrintFormatDocument):
	# Treasury sidebar section; the engine category (bank) is kept as plain
	# Python for the later template-engine stage, not as a field
	CATEGORY = "bank"
	CATEGORY_OPTIONS = ("Releve Bancaire", "Remise de Cheque", "Versement Espece")
	OWNER_FIELDS = ("bank", "beneficiary")

	def applicable_owner_fields(self) -> tuple[str, ...]:
		# the bank is required for every category; the beneficiary name only
		# exists on Remise de Cheque / Versement Espece and is cleared for
		# Releve Bancaire (the bank statement carries no name)
		if self.category == "Releve Bancaire":
			return ("bank",)
		return self.OWNER_FIELDS
