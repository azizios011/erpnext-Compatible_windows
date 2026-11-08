# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Envoi Multiple des documents: upload files and create one Facturation
document per file (supplier/customer/bank_account filled later on the form;
the MVT/journal come from the normal autoname)."""

import json

import frappe
from frappe import _
from frappe.utils import cint

from erpnext.custom_modules.facturation.facturation_base import JOURNAL_BY_DOCTYPE
from erpnext.custom_modules.organization.context import (
	require_context,
	validate_date_in_exercice,
	validate_exercice_open,
)

FACTURATION_DOCTYPES = tuple(JOURNAL_BY_DOCTYPE)
# File records attached to one of these doctypes are considered consumed
ATTACHED_DOCTYPES = tuple(FACTURATION_DOCTYPES)

PER_FILE_SAVEPOINT = "envoi_multiple_file"


@frappe.whitelist()
def get_upload_targets() -> dict:
	"""Type document options: the Facturation doctypes the user may create,
	grouped Payable / Receivable / Treasury / Declaration."""
	groups = {
		"Payable": ("Facture Achat", "RS Achat", "Releve Achat"),
		"Receivable": ("Facture Vente", "RS Vente", "Releve Vente"),
		"Treasury": ("Releve Bancaire", "Remise de Cheque", "Versement Espece"),
		"Declaration": ("Mensuelle",),
	}
	out = []
	for group, doctypes in groups.items():
		allowed = [doctype for doctype in doctypes if frappe.has_permission(doctype, "create")]
		if allowed:
			out.append({"group": _(group), "doctypes": allowed})
	return {"groups": out}


@frappe.whitelist()
def send_documents(doctype: str, month: int, year: int, files: str) -> dict:
	"""Create one Facturation document per uploaded file_url.

	Files already attached to a Facturation document are skipped; one
	failure rolls back only its own savepoint. The File record is re-attached
	to the created document (attached_to_field = attachment). The documents
	belong to the dock context's Entreprise/Exercice: a closed Exercice or a
	month outside it is refused."""
	if doctype not in FACTURATION_DOCTYPES:
		frappe.throw(_("{0} is not a Facturation document").format(doctype))
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted to create {0}").format(doctype), frappe.PermissionError)

	month = cint(month)
	year = cint(year)
	if not 1 <= month <= 12 or not year:
		frappe.throw(_("Choose a month and a year."))

	urls = json.loads(files or "[]")
	if not urls:
		frappe.throw(_("No files to attach."))

	context = require_context()
	validate_exercice_open(context)
	posting_date = f"{year:04d}-{month:02d}-01"
	validate_date_in_exercice(posting_date, context, _("Date piece"))

	results = []
	for index, file_url in enumerate(urls):
		savepoint = f"{PER_FILE_SAVEPOINT}_{index}"
		try:
			frappe.db.savepoint(savepoint)
			attached_to = _attached_to_facturation(file_url)
			if attached_to:
				# already consumed by a Facturation document: skipped, not an error
				results.append(
					{"file_url": file_url, "name": attached_to, "ok": 1, "skipped": 1, "error": ""}
				)
				continue
			name = _create_document(doctype, file_url, posting_date)
			_attach_file(file_url, doctype, name)
			results.append({"file_url": file_url, "name": name, "ok": 1, "skipped": 0, "error": ""})
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			results.append({"file_url": file_url, "name": "", "ok": 0, "error": str(error)})

	return {"results": results}


def _attached_to_facturation(file_url: str) -> str:
	"""The Facturation document already carrying this file_url, if any."""
	return frappe.db.get_value(
		"File",
		{"file_url": file_url, "attached_to_doctype": ("in", ATTACHED_DOCTYPES)},
		"attached_to_name",
	)


def _create_document(doctype: str, file_url: str, posting_date: str) -> str:
	"""Create the upload document with the base fields only. The Entreprise
	and Exercice come from the context through the doctype's before_insert."""
	doc = frappe.new_doc(doctype)
	doc.posting_date = posting_date
	doc.attachment = file_url
	doc.status = "Pending"
	if doc.meta.has_field("ocr_status"):
		doc.ocr_status = "Non traite"
	doc.insert(ignore_mandatory=True)
	return doc.name


def _attach_file(file_url: str, doctype: str, docname: str) -> None:
	frappe.db.set_value(
		"File",
		{"file_url": file_url},
		{
			"attached_to_doctype": doctype,
			"attached_to_name": docname,
			"attached_to_field": "attachment",
		},
		update_modified=False,
	)
