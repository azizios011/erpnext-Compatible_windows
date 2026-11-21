# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class DeclarationPrintFormat(PrintFormatDocument):
	# Declaration sidebar section; the engine category (other) is kept as
	# plain Python for the later template-engine stage, not as a field
	CATEGORY = "other"
	SINGLE_LAYOUT = True
	CATEGORY_OPTIONS = ("Mensuelle",)
	OWNER_FIELDS = ("month",)
