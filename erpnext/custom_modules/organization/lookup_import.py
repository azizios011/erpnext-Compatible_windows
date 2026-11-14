# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""One-shot xlsx import for the Entreprise lookup doctypes.

Triggered from each doctype's form button ("Importer depuis Excel") and from
bench console when the lookup tables are handed over as Excel files. The file
travels as a base64 payload (no File record needed) and is parsed like the plan
comptable importer: every sheet, one header row matched case- and
accent-insensitively against each field's aliases, empty rows skipped, and
per-row errors reported instead of aborting the whole run. Rows that already
exist are never overwritten.

The pure helpers carry no frappe imports so they can be verified with plain
python."""

import base64
import binascii
import io
import re
import unicodedata

import frappe
from frappe import _
from openpyxl import load_workbook

# doctype -> fieldname -> (header aliases, display label). The header row is
# matched against the aliases case- and accent-insensitively.
LOOKUP_FIELDS = {
	"Forme Juridique": {
		"forme_juridique_name": (("forme juridique", "nom", "name", "libelle", "libellé"), "Forme Juridique"),
		"code": (("code",), "Code"),
	},
	"Activite": {
		"code": (("code", "code activite"), "Code"),
		"libelle": (("libelle", "libellé"), "Libelle"),
	},
	"Convention Collective": {
		"code": (("code", "code convention"), "Code"),
		"libelle": (("libelle", "libellé"), "Libelle"),
		"nombre_jours": (("nombre de jours", "jours"), "Nombre de jours"),
		"droit_conge": (("droit au conge", "droit de conge", "droit conge", "congé", "conges"), "Droit au conge"),
	},
}

REQUIRED_FIELDS = {
	"Forme Juridique": ("forme_juridique_name",),
	"Activite": ("code", "libelle"),
	"Convention Collective": ("code", "libelle", "nombre_jours", "droit_conge"),
}

MAX_LABEL_LENGTH = 255
ERROR_PREVIEW = 50


# ── pure helpers (no frappe) ──────────────────────────────────────────────────
def _as_text(value) -> str:
	"""Cell value -> clean text; xlsx numbers become plain strings."""
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value).strip()


def _header_key(value) -> str:
	"""Case- and accent-insensitive header key ("Libellé" -> "libelle")."""
	text = _as_text(value).lower()
	return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _cell(cells, index):
	return cells[index] if index < len(cells) else None


def parse_lookup_workbook(content: bytes, doctype: str):
	"""Parse an xlsx lookup workbook for `doctype`.

	Returns (rows, errors):

	- rows: [{sheet, row, name, data}] — one entry per non-empty data row;
	  `name` is the record name the row will create (code, or the forme
	  juridique label) and `data` the field dict;
	- errors: [{sheet, row, message}] — one entry per problem (missing
	  required value, bad number, duplicate code, no header...)."""
	aliases = LOOKUP_FIELDS[doctype]
	required = REQUIRED_FIELDS[doctype]
	rows: list[dict] = []
	errors: list[dict] = []
	seen: set[str] = set()
	workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	try:
		for sheet in workbook.worksheets:
			sheet_name = sheet.title
			columns = None
			for row_number, cells in enumerate(sheet.iter_rows(values_only=True), start=1):
				if columns is None:
					# preamble rows are consumed while looking for the header
					texts = [_as_text(cell) for cell in cells]
					bound = {}
					for fieldname, (alias_list, _label) in aliases.items():
						for index, text in enumerate(texts):
							if _header_key(text) in alias_list and fieldname not in bound:
								bound[fieldname] = index
					if all(fieldname in bound for fieldname in required):
						columns = bound
					continue

				values = {
					fieldname: _as_text(_cell(cells, index)) for fieldname, index in columns.items()
				}
				if not any(values.values()):
					continue  # empty row

				row_errors = []
				name_key = "forme_juridique_name" if doctype == "Forme Juridique" else "code"
				name = values.get(name_key, "")

				for fieldname in required:
					if not values[fieldname]:
						row_errors.append(
							f"La colonne {aliases[fieldname][1]} est obligatoire (ligne {row_number})."
						)

				if name and name in seen:
					row_errors.append(f"La valeur {name} apparaît déjà dans le fichier.")
				elif name:
					seen.add(name)

				data = {}
				for fieldname, value in values.items():
					if not value:
						continue
					if fieldname in ("nombre_jours", "droit_conge"):
						number = value.replace(",", ".")
						if not re.fullmatch(r"\d+(\.\d+)?", number):
							row_errors.append(
								f"{aliases[fieldname][1]}: {value} n'est pas un nombre positif."
							)
							continue
						data[fieldname] = float(number)
					else:
						if len(value) > MAX_LABEL_LENGTH:
							row_errors.append(
								f"{aliases[fieldname][1]} dépasse {MAX_LABEL_LENGTH} caractères."
							)
							continue
						data[fieldname] = value

				for message in row_errors:
					errors.append({"sheet": sheet_name, "row": row_number, "message": message})
				if not row_errors:
					rows.append({"sheet": sheet_name, "row": row_number, "name": name, "data": data})
			if columns is None:
				errors.append(
					{
						"sheet": sheet_name,
						"row": None,
						"message": "En-tête introuvable: il faut les colonnes "
						+ ", ".join(aliases[fieldname][1] for fieldname in required)
						+ ".",
					}
				)
	finally:
		workbook.close()
	return rows, errors


# ── whitelisted entry point ───────────────────────────────────────────────────
@frappe.whitelist()
def import_lookup_xlsx(doctype: str, content_base64: str, dry_run: int = 0) -> dict:
	"""Importe un fichier xlsx de lignes (Forme Juridique, Activite,
	Convention Collective). dry_run=1: contrôle seulement, rien n'est écrit."""
	try:
		return _import_lookup_xlsx(doctype, content_base64, dry_run)
	except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError):
		raise  # expected failures already carry their French message
	except Exception:
		frappe.db.rollback()
		frappe.log_error("axeane lookup import failed", frappe.get_traceback())
		frappe.throw(
			_("Une erreur inattendue a interrompu l'import (voir Error Log)."),
			title=_("Import"),
		)


def _import_lookup_xlsx(doctype: str, content_base64: str, dry_run: int) -> dict:
	if doctype not in LOOKUP_FIELDS:
		frappe.throw(
			_("Ce doctype n'accepte pas d'import Excel: {0}.").format(doctype),
			frappe.PermissionError,
		)
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(
			_("Vous n'avez pas le droit de créer des {0}.").format(_(doctype)),
			frappe.PermissionError,
		)
	try:
		content = base64.b64decode(content_base64 or "", validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("Fichier illisible (base64 invalide)."), title=_("Fichier invalide"))

	rows, errors = parse_lookup_workbook(content, doctype)
	existing = set(frappe.get_all(doctype, pluck="name"))
	deja_existants = sum(1 for row in rows if row["name"] in existing)

	summary = {
		"ok": len(errors) == 0,
		"doctype": doctype,
		"total": len(rows),
		"created": 0,
		"deja_existants": deja_existants,
		"errors": errors[:ERROR_PREVIEW],
		"error_count": len(errors),
	}

	if dry_run:
		return summary
	if summary["error_count"] > 0:
		summary["ok"] = False
		return summary

	for row in rows:
		if row["name"] in existing:
			continue  # existing rows are never overwritten
		doc = frappe.new_doc(doctype)
		doc.update(row["data"])
		doc.insert()
		summary["created"] += 1
	frappe.db.commit()
	return summary
