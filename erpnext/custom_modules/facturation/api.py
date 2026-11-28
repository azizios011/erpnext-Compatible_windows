# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Envoi Multiple des documents: upload files and create one Facturation
document per file (supplier/customer/bank_account filled later on the form;
the MVT/journal come from the normal autoname)."""

import json
import os

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from erpnext.custom_modules.facturation.facturation_base import JOURNAL_BY_DOCTYPE
from erpnext.custom_modules.facturation import mensuelle_checks, mensuelle_workbook
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

# ── Mensuelle workbook import (goal: one Mensuelle per monthly sheet) ────────

MENSUELLE_DOCTYPE = "Mensuelle"
DECLARATION_DOCTYPE = "Declaration Transaction"


def _resolve_local_path(file_url: str) -> str:
	"""The on-disk path of an uploaded private/public file."""
	file_path = frappe.utils.file_manager.get_file_path(file_url or "")
	if not file_path or not os.path.exists(file_path):
		frappe.throw(_("Fichier introuvable sur le serveur: {0}").format(file_url or ""))
	return file_path


def _normalize_matricule(value: str) -> str:
	return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _check_sheet_header(extracted: dict, matricule: str, expected_year: int) -> list[str]:
	"""The header checks beyond the extraction errors: the tax ID must match
	the context Entreprise's matricule fiscal, the year the context Exercice's
	annee, and the sheet-name month the header digits."""
	errors = list(extracted.get("errors") or [])
	sheet_tax_id = _normalize_matricule(extracted.get("tax_id") or "")
	if matricule:
		if not sheet_tax_id:
			errors.append(_("Identifiant fiscal absent de l'entete de la feuille."))
		elif sheet_tax_id != matricule[: len(sheet_tax_id)]:
			errors.append(
				_("Identifiant fiscal de l'entete ({0}) different du matricule de l'entreprise ({1}).").format(
					sheet_tax_id, matricule
				)
			)
	year = (extracted.get("year") or "").strip()
	if expected_year and year and year != str(expected_year):
		errors.append(_("Annee de l'entete ({0}) differente de l'exercice courant ({1}).").format(year, expected_year))
	sheet_month = mensuelle_workbook.parse_sheet_month(extracted.get("sheet") or "")
	header_month = (extracted.get("month") or "").strip()
	if sheet_month and header_month and header_month != f"{sheet_month:02d}":
		errors.append(
			_("Mois de l'entete ({0}) different du mois de la feuille ({1:02d}).").format(header_month, sheet_month)
		)
	return errors


def _existing_mensuelle(entreprise: str, exercice: str, month: str) -> dict | None:
	"""The Mensuelle of the same entreprise / exercice / month, if any."""
	name = frappe.db.get_value(
		MENSUELLE_DOCTYPE,
		{"entreprise": entreprise, "exercice": exercice, "period_month": month},
		["name", "status"],
		as_dict=True,
	)
	return name


def _existing_declaration(entreprise: str, exercice: str, month: str) -> dict | None:
	"""The month's ledger-computed Declaration Transaction (Principale)."""
	name = frappe.db.get_value(
		DECLARATION_DOCTYPE,
		{
			"entreprise": entreprise,
			"exercice": exercice,
			"mois": month,
			"type_declaration": "Principale",
		},
		["name", "status"],
		as_dict=True,
	)
	return name


@frappe.whitelist(methods=["POST"])
def preview_mensuelle_workbook(file_url: str) -> dict:
	"""Dry run over one Déclaration Mensuelle workbook: one row per monthly
	sheet with its month, layout, header/extraction errors and whether a
	Mensuelle document already exists. Nothing is written."""
	if not frappe.has_permission(MENSUELLE_DOCTYPE, "create"):
		frappe.throw(_("Not permitted to create {0}").format(MENSUELLE_DOCTYPE), frappe.PermissionError)
	context = require_context()
	validate_exercice_open(context)

	matricule = _normalize_matricule(
		frappe.db.get_value("Entreprise", context["entreprise"], "matricule_fiscal") or ""
	)
	expected_year = frappe.db.get_value("Exercice", context["exercice"], "annee")

	payload = mensuelle_workbook.extract_workbook(_resolve_local_path(file_url))
	sheets = []
	for extracted in payload["sheets"]:
		month_number = mensuelle_workbook.parse_sheet_month(extracted["sheet"])
		month = f"{month_number:02d}" if month_number else ""
		errors = _check_sheet_header(extracted, matricule, expected_year)
		existing = _existing_mensuelle(context["entreprise"], context["exercice"], month) if month else None
		declaration = _existing_declaration(context["entreprise"], context["exercice"], month) if month else None
		sheets.append(
			{
				"sheet": extracted["sheet"],
				"month": month,
				"layout": extracted["layout"],
				"errors": errors,
				"ok": 1 if not errors else 0,
				"existing_mensuelle": existing.name if existing else "",
				"existing_status": existing.status if existing else "",
				"declaration": declaration.name if declaration else "",
				"declaration_status": declaration.status if declaration else "",
			}
		)
	return {
		"file_url": file_url,
		"entreprise": context["entreprise"],
		"exercice": context["exercice"],
		"sheets": sheets,
		"recap_months": sorted(payload["recap"].keys()),
	}


def _mensuelle_lines(extracted: dict) -> list[dict]:
	"""The declared figures as Mensuelle Ligne rows, mapped to the Axeane
	rubrique codes. For RS 1% and RS 3% the AMOUNT is the typed value (the
	base is back-derived in the sheet) — both travel as declared."""
	rows = []
	for mapping in mensuelle_workbook.RUBRIQUE_MAP:
		base = (extracted["figures"].get(mapping["base"]) or {}) if mapping["base"] else {}
		montant = extracted["figures"].get(mapping["montant"]) or {}
		if montant.get("value") is None and not (base.get("value") is not None):
			continue
		formula = montant.get("formula") or base.get("formula") or ""
		rows.append(
			{
				"code_rubrique": mapping["code"],
				"libelle": mapping["libelle"],
				"base_declaree": float(base["value"]) if base.get("value") is not None else None,
				"montant_declare": float(montant["value"]) if montant.get("value") is not None else None,
				"source_cell": montant.get("cell") or "",
				"raw_formula": str(formula) if formula else "",
			}
		)
	# the taxable pay (the sheet's own cell): the RECAP's S.IMPOS column and
	# the derived CNSS (S.BRUT - S.IMPOS) read it — no Declaration Transaction
	# counterpart, so the checks skip it
	s_impos = extracted["figures"].get("s_impos") or {}
	if s_impos.get("value") is not None:
		rows.append(
			{
				"code_rubrique": "S_IMPOS",
				"libelle": "Salaire imposable",
				"base_declaree": float(s_impos["value"]),
				"montant_declare": None,
				"source_cell": s_impos.get("cell") or "",
				"raw_formula": str(s_impos.get("formula") or ""),
			}
		)
	return rows


def _attach_sheet_file(source_path: str, sheet_name: str, docname: str, month: str, year: int) -> str:
	"""The values-only single-sheet copy as a PRIVATE File attached to the
	Mensuelle (the XLSX view reads it). Returns the file_url."""
	content = mensuelle_workbook.build_sheet_copy(source_path, sheet_name)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"DM_{year}_{month}_declaree.xlsx",
			"is_private": 1,
			"attached_to_doctype": MENSUELLE_DOCTYPE,
			"attached_to_name": docname,
			"attached_to_field": "sheet_file",
			"folder": "Home/Attachments",
			"content": content,
		}
	)
	file_doc.insert(ignore_permissions=True)
	return file_doc.file_url


@frappe.whitelist(methods=["POST"])
def import_mensuelle_workbook(file_url: str, overwrite: int = 0) -> dict:
	"""Create one Mensuelle (status Pending) per monthly sheet of the
	workbook. Duplicates (same entreprise, exercice, month) are skipped, or
	replaced only when overwrite=1 and their status is still Pending. One
	failing sheet rolls back its own savepoint."""
	if not frappe.has_permission(MENSUELLE_DOCTYPE, "create"):
		frappe.throw(_("Not permitted to create {0}").format(MENSUELLE_DOCTYPE), frappe.PermissionError)
	context = require_context()
	validate_exercice_open(context)
	entreprise, exercice = context["entreprise"], context["exercice"]
	expected_year = frappe.db.get_value("Exercice", exercice, "annee")
	overwrite = cint(overwrite)

	matricule = _normalize_matricule(
		frappe.db.get_value("Entreprise", entreprise, "matricule_fiscal") or ""
	)
	source_path = _resolve_local_path(file_url)
	payload = mensuelle_workbook.extract_workbook(source_path)

	results = []
	first_created = False
	for extracted in payload["sheets"]:
		month_number = mensuelle_workbook.parse_sheet_month(extracted["sheet"])
		month = f"{month_number:02d}" if month_number else ""
		errors = _check_sheet_header(extracted, matricule, expected_year)
		if errors:
			results.append({"sheet": extracted["sheet"], "month": month, "ok": 0, "skipped": 0, "replaced": 0, "name": "", "error": " ; ".join(errors)})
			continue

		savepoint = "mensuelle_sheet"
		try:
			frappe.db.savepoint(savepoint)
			existing = _existing_mensuelle(entreprise, exercice, month)
			if existing and not (overwrite and existing.status == "Pending"):
				frappe.db.rollback(save_point=savepoint)
				reason = (
					_("existe deja (statut {0})").format(existing.status)
					if not overwrite
					else _("statut {0}: seul un document Pending est remplacable").format(existing.status)
				)
				results.append(
					{"sheet": extracted["sheet"], "month": month, "ok": 1, "skipped": 1, "replaced": 0, "name": existing.name, "error": reason}
				)
				continue

			total_figure = (extracted["figures"].get("total") or {}).get("value")
			values = {
				"posting_date": f"{expected_year:04d}-{month}-01",
				"period_month": month,
				"period_year": expected_year,
				"reference_number": f"DM {month}",
				"status": "Pending",
				"ocr_status": "Non traite",
				"attachment": file_url,
				"source_file": file_url,
				"source_sheet": extracted["sheet"],
				"layout_profile": extracted["layout"] or "",
				"declared_total": float(total_figure) if total_figure is not None else None,
				"check_status": "Non verifie",
				"lignes": _mensuelle_lines(extracted),
			}

			if existing:
				doc = frappe.get_doc(MENSUELLE_DOCTYPE, existing.name)
				doc.set("lignes", [])
				for key, value in values.items():
					if key == "lignes":
						continue
					doc.set(key, value)
				doc.save()
				replaced = 1
			else:
				doc = frappe.new_doc(MENSUELLE_DOCTYPE)
				for key, value in values.items():
					if key == "lignes":
						continue
					doc.set(key, value)
				for line in values["lignes"]:
					doc.append("lignes", {k: v for k, v in line.items() if v is not None})
				doc.insert()
				replaced = 0

			# the values-only single-sheet copy (private), attached to the doc
			sheet_url = _attach_sheet_file(source_path, extracted["sheet"], doc.name, month, expected_year)
			frappe.db.set_value(
				MENSUELLE_DOCTYPE,
				doc.name,
				"sheet_file",
				sheet_url,
				update_modified=False,
			)

			# the uploaded workbook's File record follows the first created doc
			if not first_created:
				frappe.db.set_value(
					"File",
					{"file_url": file_url},
					{
						"attached_to_doctype": MENSUELLE_DOCTYPE,
						"attached_to_name": doc.name,
						"attached_to_field": "attachment",
					},
					update_modified=False,
				)
				first_created = True

			results.append(
				{"sheet": extracted["sheet"], "month": month, "ok": 1, "skipped": 0, "replaced": replaced, "name": doc.name, "error": ""}
			)
		except Exception as error:
			frappe.db.rollback(save_point=savepoint)
			results.append(
				{"sheet": extracted["sheet"], "month": month, "ok": 0, "skipped": 0, "replaced": 0, "name": "", "error": str(error)}
			)

	return {"file_url": file_url, "results": results}


def _declaration_payload(entreprise: str, exercice: str, month: str) -> dict | None:
	"""The month's Principale Declaration Transaction as the pure checks read
	it (lines + totals), or None when the month was never computed."""
	name = frappe.db.get_value(
		DECLARATION_DOCTYPE,
		{
			"entreprise": entreprise,
			"exercice": exercice,
			"mois": month,
			"type_declaration": "Principale",
		},
		"name",
	)
	if not name:
		return None
	doc = frappe.get_doc(DECLARATION_DOCTYPE, name)
	return {
		"name": doc.name,
		"status": doc.status,
		"lines": [
			{
				"code": line.code,
				"montant_brut": float(line.montant_brut or 0),
				"retenu": float(line.retenu or 0),
			}
			for line in (doc.rubriques or [])
		],
		"tva_collectee": float(doc.tva_collectee or 0),
		"tva_deductible": float(doc.tva_deductible or 0),
		"tva_a_payer": float(doc.tva_a_payer or 0),
		"credit_suivant": float(doc.credit_suivant or 0),
		"total_a_payer": float(doc.total_a_payer or 0),
	}


def _sheet_check_payload(extracted: dict) -> dict:
	"""The extraction + the declared rubrique figures (the RUBRIQUE_MAP
	mapping, S_IMPOS excluded: it has no Declaration Transaction
	counterpart), so the checks' family C compares per rubrique."""
	rubriques = []
	for mapping in mensuelle_workbook.RUBRIQUE_MAP:
		base = None
		if mapping["base"]:
			base = (extracted["figures"].get(mapping["base"]) or {}).get("value")
		montant = (extracted["figures"].get(mapping["montant"]) or {}).get("value")
		rubriques.append({"code": mapping["code"], "base": base, "montant": montant})
	return {**extracted, "rubriques": rubriques}


@frappe.whitelist(methods=["POST"])
def verify_mensuelle(name: str) -> dict:
	"""Re-run the three check families over the stored source sheet and store
	the Controle rows, the check_status and checked_at."""
	doc = frappe.get_doc(MENSUELLE_DOCTYPE, name)
	doc.check_permission("write")
	context = require_context()
	if doc.entreprise != context["entreprise"] or doc.exercice != context["exercice"]:
		frappe.throw(_("La Mensuelle {0} appartient a un autre contexte comptable.").format(name))
	if not (doc.source_file and doc.source_sheet):
		frappe.throw(_("Aucune feuille source: cette Mensuelle n'a pas ete importee depuis un classeur."))

	payload = mensuelle_workbook.extract_workbook(_resolve_local_path(doc.source_file))
	extracted = next(
		(
			sheet
			for sheet in payload["sheets"]
			if sheet["sheet"].strip().lower() == doc.source_sheet.strip().lower()
		),
		None,
	)
	if extracted is None:
		frappe.throw(_("La feuille {0} est absente du classeur source.").format(doc.source_sheet))

	recap_row = payload["recap"].get(int(doc.period_month)) if doc.period_month else None
	dm = _declaration_payload(doc.entreprise, doc.exercice, doc.period_month)
	result = mensuelle_checks.run_checks(_sheet_check_payload(extracted), recap_row, dm)

	doc.set("controles", [])
	for control in result["controls"]:
		doc.append(
			"controles",
			{
				"check_code": control["check_code"],
				"severity": control["severity"],
				"message": control["message"],
				"declare": control["declare"],
				"attendu": control["attendu"],
				"ecart": control["ecart"],
			},
		)
	doc.check_status = result["status"]
	doc.checked_at = now_datetime()
	doc.save()
	return {"status": result["status"], "controls": result["controls"]}
