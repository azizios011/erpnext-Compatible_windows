# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Whitelisted endpoints for the Facturation Print Format templates.

Validation and preview run on the CURRENT form contents (the doc does not
need to be saved first). Every function is System Manager only and fully
type-annotated; the heavy lifting is delegated to the frappe-free
template_validators package."""

import json
import os
import shutil
import subprocess
import tempfile

import frappe
from frappe import _
from frappe.utils.pdf import get_pdf

from erpnext.custom_modules.facturation.template_validators import hash_editor_contents
from erpnext.custom_modules.facturation.template_validators.registry import get_validator

PRINT_FORMAT_DOCTYPES = (
	"Payable Print Format",
	"Receivable Print Format",
	"Treasury Print Format",
	"Declaration Print Format",
)


def _timeout() -> int:
	return int(frappe.db.get_single_value("Document Template Settings", "build_timeout_seconds") or 30)


def _validator(category: str):
	validator = get_validator(category or "")
	if not validator:
		frappe.throw(_("No validator for {0} yet.").format(_(category or "")))
	return validator


def _files(editor_mode: str, html_code: str, css_code: str, python_code: str) -> dict:
	return {"html": html_code or "", "css": css_code or "", "python": python_code or ""}


def _collect_args(template: str, template_doctype: str, category: str, editor_mode: str, html_code: str, css_code: str, python_code: str) -> tuple:
	if template_doctype and template_doctype not in PRINT_FORMAT_DOCTYPES:
		frappe.throw(_("{0} is not a Facturation Print Format doctype.").format(_(template_doctype)))
	mode = editor_mode or "HTML/CSS"
	files = _files(mode, html_code, css_code, python_code)
	code_hash = hash_editor_contents(mode, html_code, css_code, python_code)
	return mode, files, code_hash


def _persist_validation(template: str, template_doctype: str, result: dict, code_hash: str) -> None:
	if not template or not template_doctype:
		return
	if not frappe.db.exists(template_doctype, template):
		return
	frappe.db.set_value(
		template_doctype,
		template,
		{
			"validation_status": result["status"],
			"validation_log": "\n".join(result["log"]),
			"extraction_schema": json.dumps(result["schema"], indent=1),
			"validated_hash": code_hash,
			"validated_on": frappe.utils.now_datetime(),
		},
	)


@frappe.whitelist(methods=["POST"])
def validate_print_format(template: str, template_doctype: str, category: str, editor_mode: str, html_code: str, css_code: str, python_code: str) -> dict:
	"""Validate the current editor contents against the doctype validator;
	persists the result on the record when it is already saved."""
	frappe.only_for("System Manager")
	validator = _validator(category)
	mode, files, code_hash = _collect_args(
		template, template_doctype, category, editor_mode, html_code, css_code, python_code
	)
	result = validator.validate(mode=mode, files=files, timeout=_timeout())
	_persist_validation(template, template_doctype, result, code_hash)
	return {
		"status": result["status"],
		"log": "\n".join(result["log"]),
		"schema": json.dumps(result["schema"], indent=1),
		"validated_hash": code_hash,
		"validated_on": frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
	}


@frappe.whitelist(methods=["POST"])
def preview_print_format(template: str, template_doctype: str, category: str, editor_mode: str, html_code: str, css_code: str, python_code: str) -> dict:
	"""Render dataset A of the current editor contents: HTML/CSS becomes a
	PDF (the chrome generator frappe already uses), Python produces the xlsx
	(converted to PDF when LibreOffice is available). No persistence beyond
	the preview file itself."""
	frappe.only_for("System Manager")
	validator = _validator(category)
	mode, files, _code_hash = _collect_args(
		template, template_doctype, category, editor_mode, html_code, css_code, python_code
	)
	try:
		schema, errors, _warnings = validator.resolve_schema(mode=mode, files=files)
	except ValueError as error:
		frappe.throw(str(error))
	if errors:
		frappe.throw(
			_("The template does not satisfy the contract: {0}").format("; ".join(errors))
		)
	dataset = validator.sample_datasets(schema)[0]["data"]
	with tempfile.TemporaryDirectory() as tmp:
		try:
			paths = validator.generate(mode=mode, files=files, data=dataset, out_dir=tmp, timeout=_timeout())
		except (RuntimeError, TimeoutError) as error:
			frappe.throw(_("Preview failed: {0}").format(error))
		if not paths or not os.path.isfile(paths[0]):
			frappe.throw(_("Preview failed: the template produced no output."))
		output = paths[0]
		if mode == "HTML/CSS":
			with open(output, "r", encoding="utf-8") as handle:
				content = get_pdf(handle.read())
			kind, extension = "pdf", "pdf"
		else:
			pdf_path = _xlsx_to_pdf(output, tmp)
			if pdf_path:
				output, kind, extension = pdf_path, "pdf", "pdf"
			else:
				kind, extension = "xlsx", "xlsx"
			with open(output, "rb") as handle:
				content = handle.read()
	file_doc = frappe.get_doc({
		"doctype": "File",
		"file_name": f"preview-{frappe.scrub(category or 'template')}-dataset-a.{extension}",
		"is_private": 1,
		"content": content,
		"attached_to_doctype": template_doctype or None,
		"attached_to_name": template or None,
	})
	file_doc.insert()
	return {"file_url": file_doc.file_url, "kind": kind}


def _xlsx_to_pdf(xlsx_path: str, out_dir: str) -> str | None:
	"""Best-effort LibreOffice conversion, the exporter the tunisian_univer
	engine already relies on; None keeps the xlsx as the preview."""
	binary = shutil.which("soffice") or shutil.which("libreoffice")
	if not binary and os.path.isfile("/usr/lib/libreoffice/program/soffice"):
		binary = "/usr/lib/libreoffice/program/soffice"
	if not binary:
		return None
	try:
		subprocess.run(
			[binary, "--headless", "--convert-to", "pdf:calc_pdf_Export", "--outdir", out_dir, xlsx_path],
			capture_output=True,
			timeout=90,
			check=False,
		)
	except Exception:  # noqa: BLE001 — conversion is best effort
		return None
	pdf_path = os.path.splitext(xlsx_path)[0] + ".pdf"
	return pdf_path if os.path.isfile(pdf_path) else None
