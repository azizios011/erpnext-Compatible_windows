# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.print_format_base import PrintFormatDocument


class DeclarationPrintFormat(PrintFormatDocument):
	# Declaration sidebar section: declaration documents; one layout per
	# company (other: layout_id "default" only)
	CATEGORY = "other"
	APPLIES_TO = ("Mensuelle",)
