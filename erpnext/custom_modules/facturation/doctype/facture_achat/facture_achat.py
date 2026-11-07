# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from erpnext.custom_modules.facturation.facturation_base import FacturationDocument


class FactureAchat(FacturationDocument):
	journal_code = "AC"
