# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate

from erpnext.custom_modules.facturation.facturation_base import attachment_file_name

# The Payable/Receivable list views are built on real docfields; this fills
# them on the records created before the columns existed.
LIST_DOCTYPES = (
	"Facture Achat",
	"RS Achat",
	"Releve Achat",
	"Facture Vente",
	"RS Vente",
	"Releve Vente",
)

NEW_FIELDS = ("transfer_date", "sent_by", "file_name")


def execute():
	"""Backfill the new list columns on existing rows: transfer_date comes
	from creation, sent_by from owner and file_name the attachment's base
	name. frappe.db.set_value fires no hooks and leaves modified untouched,
	so lists keep their order. A doctype whose sync has not added the
	columns yet is skipped."""
	for doctype in LIST_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if any(not meta.has_field(field) for field in NEW_FIELDS):
			continue
		rows = frappe.get_all(
			doctype,
			or_filters=[[doctype, field, "is", "not set"] for field in NEW_FIELDS],
			fields=["name", "creation", "owner", "attachment", *NEW_FIELDS],
		)
		for row in rows:
			values = {}
			if not row.transfer_date:
				values["transfer_date"] = getdate(row.creation)
			if not row.sent_by:
				values["sent_by"] = row.owner
			if not row.file_name:
				values["file_name"] = attachment_file_name(row.attachment)
			if values:
				frappe.db.set_value(doctype, row.name, values, update_modified=False)
		if rows:
			frappe.logger("axeane").info(f"backfilled list columns on {doctype}")
