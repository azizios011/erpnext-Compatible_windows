# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe


class ChartofAccounts(Document):
	pass


@frappe.whitelist()
def get_children(doctype, parent="", **filters):
	records = frappe.get_all(
		"Chart of Accounts",
		filters={"parent_account": parent or ""},
		fields=["account", "label", "is_group"],
		order_by="account asc",
	)

	return [
		{
			"value": d.account,
			"title": f"{d.account} - {d.label}",
			"expandable": bool(d.is_group),
		}
		for d in records
	]
