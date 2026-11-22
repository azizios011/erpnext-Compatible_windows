# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The import hub engine (Organization workspace — Import Configuration).

One Import Configuration document per xlsx file type (unique target) tells
the hub how to read the file: sheet, header row, date / decimal formats and
the column map (xlsx header aliases -> target fields, matched accent- and
case-insensitively).

- validate(file_url, target): dry run — the file is read, coerced and
  checked; per-row errors come back for the dialog, nothing is written.
- import_records(file_url, target): the same validation, then an
  all-or-nothing upsert (match_on + on_duplicate Skip / Update / Error);
  any validation error refuses the run. (The method is not literally named
  `import` — that is a Python keyword.)
- template(target): a generated xlsx model carrying the configured headers.

Grand Livre and Chart of Account keep their specialized flows
(reports/ledger_import.py, plan_comptable.py) which read their column
mapping from the matching configuration — the generic engine refuses them.
The pure reading / normalization helpers (norm_text, header_key, cell,
parse_date, read_file_content) live here and feed those two flows as well.
"""

import io
import re
import unicodedata
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

# ── targets ──────────────────────────────────────────────────────────────────

# the generic targets: the engine upserts rows of the doctype directly
GENERIC_TARGETS = {
	"Entreprise": "Entreprise",
	"Forme Juridique": "Forme Juridique",
	"Convention Collective": "Convention Collective",
	"Activite": "Activite",
	"Operation Tresorerie": "Operation Tresorerie",
}

# the targets with a dedicated flow (column mapping only; the generic
# endpoints refuse them)
SPECIALIZED_TARGETS = ("Grand Livre", "Chart of Account")

IMPORT_ROLES = ("Accounts Manager", "System Manager")

# the fieldtypes the column map can carry (layout / child-table / attach
# fields are never importable)
IMPORTABLE_FIELDTYPES = ("Data", "Date", "Float", "Int", "Currency", "Percent", "Select", "Link", "Check")

MAX_PREVIEW_ERRORS = 50
MAX_PREVIEW_ROWS = 30


# ── pure helpers (shared with the Grand Livre / plan comptable readers) ──────


def norm_text(value) -> str:
	"""Text cells: stripped; an integral float loses the trailing .0 (the
	Compte 401000.0 becomes "401000", a text code keeps its leading zeros)."""
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return cstr(value).strip()


def header_key(value) -> str:
	"""Header cell -> the accent-free lowercase key the aliases match on."""
	text = norm_text(value).lower()
	return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def cell(cells: tuple, index: int):
	return cells[index] if index < len(cells) else None


def parse_date(value, date_format: str = "dd/mm/yyyy"):
	"""A real date cell or a valid text in the configured format, else None
	(invalid — reported as date invalide)."""
	if value is None:
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = str(value).strip()
	if date_format == "yyyy-mm-dd":
		pattern, year, month, day = r"(\d{4})-(\d{1,2})-(\d{1,2})", 1, 2, 3
	elif date_format == "mm/dd/yyyy":
		pattern, year, month, day = r"(\d{1,2})/(\d{1,2})/(\d{4})", 3, 1, 2
	else:  # dd/mm/yyyy (the Grand Livre's and the default format)
		pattern, year, month, day = r"(\d{1,2})/(\d{1,2})/(\d{4})", 3, 2, 1
	match = re.fullmatch(pattern, text)
	if match:
		try:
			return date(int(match.group(year)), int(match.group(month)), int(match.group(day)))
		except ValueError:
			return None  # "31/13/2026" and friends: reported as date invalide
	return None


def parse_number(value, decimal_separator: str = "."):
	"""A number cell or text with the configured decimal separator, else None
	(invalid). Thousands spaces are tolerated."""
	text = norm_text(value)
	if not text:
		return None
	if decimal_separator == ",":
		text = text.replace("\u202f", "").replace("\u00a0", "").replace(" ", "").replace(",", ".")
	try:
		return float(text)
	except ValueError:
		return None


def parse_check(value) -> int:
	text = norm_text(value).lower()
	return 1 if text in ("1", "x", "oui", "yes", "true", "vrai", "y") else 0


def read_file_content(file_url: str) -> bytes:
	"""The File document's bytes for an uploaded xlsx."""
	if not file_url:
		frappe.throw(_("A file is required."), frappe.ValidationError)
	file = frappe.get_doc("File", {"file_url": file_url})
	return file.get_content()


def split_headers(xlsx_header: str) -> list[str]:
	"""The comma-separated aliases of one column row."""
	return [part.strip() for part in str(xlsx_header or "").split(",") if part.strip()]


def alias_map(config) -> dict[str, str]:
	"""normalized header key -> target field, from the configuration's
	columns (the first alias of a column is its model header)."""
	mapping: dict[str, str] = {}
	for col in config.columns or []:
		for alias in split_headers(col.xlsx_header):
			key = header_key(alias)
			if key and key not in mapping:
				mapping[key] = col.target_field
	return mapping


# ── configuration access ─────────────────────────────────────────────────────


def get_import_config(target: str, raise_when_missing: bool = True):
	"""The enabled Import Configuration of one target, or None
	(raise_when_missing=False) for the flows that fall back to their
	hard-coded defaults."""
	name = frappe.db.get_value("Import Configuration", {"target": target, "enabled": 1})
	if not name:
		if raise_when_missing:
			frappe.throw(
				_("Pas de Import Configuration active pour {0} (créez-la dans l'espace Organization).").format(target),
				title=_("Import Configuration"),
			)
		return None
	return frappe.get_doc("Import Configuration", name)


def columns_for_doctype(doctype: str) -> list[dict]:
	"""Column rows generated from a doctype's meta: every non-hidden
	importable field with its reqd flag, default and Link lookup field (the
	linked doctype's title field, when one exists)."""
	meta = frappe.get_meta(doctype)
	columns = []
	for df in meta.get("fields") or []:
		if df.fieldtype not in IMPORTABLE_FIELDTYPES or getattr(df, "hidden", 0):
			continue
		link_lookup = ""
		if df.fieldtype == "Link" and df.options:
			link_lookup = frappe.get_meta(df.options).title_field or ""
		columns.append(
			{
				"xlsx_header": getattr(df, "label", "") or df.fieldname,
				"target_field": df.fieldname,
				"field_type": df.fieldtype,
				"required": 1 if getattr(df, "reqd", 0) else 0,
				"default_value": cstr(getattr(df, "default", "")) if getattr(df, "default", "") else "",
				"link_lookup_field": link_lookup,
			}
		)
	return columns


def check_import_hub_roles() -> None:
	if frappe.session.user == "Administrator":
		return
	if not set(IMPORT_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("Not permitted to run the import hub"), frappe.PermissionError)


def _check_can_import(doctype: str) -> None:
	"""The hub's gate: one of the import roles + create on the target doctype
	(the writes go through doc.insert / doc.save, so frappe's own permissions
	apply again on every write)."""
	check_import_hub_roles()
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted to import {0}").format(_(doctype)), frappe.PermissionError)


# ── the generic reader ───────────────────────────────────────────────────────


def _select_sheet(workbook, sheet_name: str):
	if sheet_name:
		for sheet in workbook.worksheets:
			if header_key(sheet.title) == header_key(sheet_name):
				return sheet
		frappe.throw(_("La feuille {0} est introuvable dans le fichier.").format(sheet_name), title=_("Import"))
	return workbook.worksheets[0]


def read_workbook_rows(file_url: str, config) -> tuple[list[dict], list[str]]:
	"""Read + map one sheet: returns (rows, problems) where each row carries
	{target_field: raw value, "_row": spreadsheet row number}. The header row
	comes from config.header_row: the declared row is tried first, and the
	reader falls back to scanning for the row that covers the required
	columns (the Grand Livre reader's tolerance of preamble rows) when it
	doesn't — or when header_row is 0. Rows whose cells are all empty are
	skipped. Problems are hard blockers (bad or missing header row)."""
	from openpyxl import load_workbook

	content = read_file_content(file_url)
	workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	rows: list[dict] = []
	problems: list[str] = []
	mapping = alias_map(config)
	all_fields = [col.target_field for col in config.columns or []]
	required = [col.target_field for col in config.columns or [] if col.required] or all_fields
	header_row = cint(config.header_row)

	def header_map(cells) -> dict[str, int] | None:
		mapped: dict[str, int] = {}
		for index, raw in enumerate(cells):
			field = mapping.get(header_key(raw))
			if field and field not in mapped:
				mapped[field] = index
		return mapped if all(field in mapped for field in required) else None

	try:
		sheet = _select_sheet(workbook, config.sheet_name)
		numbered_rows = list(enumerate(sheet.iter_rows(values_only=True), start=1))
		columns: dict[str, int] = None
		header_found_at = 0
		if header_row:
			# the declared position first (the configuration knows its file)
			for row_number, cells in numbered_rows:
				if row_number == header_row:
					columns = header_map(cells)
					if columns:
						header_found_at = row_number
					break
		if columns is None:
			# tolerant scan: preamble rows above the header are consumed
			for row_number, cells in numbered_rows:
				columns = header_map(cells)
				if columns:
					header_found_at = row_number
					break
		if columns is None:
			problems.append(_("En-tete invalide: colonnes {0} attendues.").format(", ".join(required)))
			return rows, problems

		for row_number, cells in numbered_rows:
			if row_number <= header_found_at:
				continue  # the header row itself (and anything above it)
			values = {field: cell(cells, index) for field, index in columns.items()}
			if all(value is None or norm_text(value) == "" for value in values.values()):
				continue  # empty row
			values["_row"] = row_number
			rows.append(values)
	finally:
		workbook.close()
	return rows, problems


# ── coercion + validation ────────────────────────────────────────────────────


def _resolve_link(link_doctype: str, lookup_field: str, raw: str) -> str:
	"""Resolve a Link cell by exact name, then by the lookup field (the
	linked doctype's title field when configured), then by containment. One
	match resolves; none or several are row errors."""
	if frappe.db.exists(link_doctype, raw):
		return raw
	field = lookup_field or (frappe.get_meta(link_doctype).title_field or "")
	if field:
		matches = frappe.get_all(link_doctype, filters={field: raw}, pluck="name")
		if not matches:
			matches = frappe.get_all(link_doctype, filters={field: ("like", f"%{raw}%")}, pluck="name")
	else:
		matches = []
	if len(matches) == 1:
		return matches[0]
	if not matches:
		frappe.throw(_("introuvable dans {0}").format(_(link_doctype)), frappe.ValidationError)
	frappe.throw(
		_("ambigu dans {0}: {1} correspondances").format(_(link_doctype), len(matches)), frappe.ValidationError
	)


def coerce_row(row: dict, config, meta) -> tuple[dict | None, list[str]]:
	"""One raw row -> typed values (or per-row error messages). Empty cells
	take the column's default; required columns refuse empties; Select values
	must be in the target field's options; Link cells are resolved."""
	errors: list[str] = []
	values: dict = {}
	for col in config.columns or []:
		fieldname = col.target_field
		raw = row.get(fieldname)
		text = norm_text(raw)
		field_type = col.field_type or "Data"
		header = split_headers(col.xlsx_header)[0] if split_headers(col.xlsx_header) else fieldname
		if not text:
			if col.default_value:
				text = col.default_value
			elif cint(col.required):
				errors.append(_("colonne {0} obligatoire.").format(header))
				continue
			else:
				continue

		try:
			if field_type == "Date":
				parsed = parse_date(raw, config.date_format or "dd/mm/yyyy")
				if parsed is None:
					frappe.throw(_("date invalide ({0}).").format(text), frappe.ValidationError)
				values[fieldname] = parsed
			elif field_type in ("Float", "Currency", "Percent"):
				parsed = parse_number(raw, config.decimal_separator or ".")
				if parsed is None:
					frappe.throw(_("nombre invalide ({0}).").format(text), frappe.ValidationError)
				values[fieldname] = flt(parsed, 3)
			elif field_type == "Int":
				parsed = parse_number(raw, config.decimal_separator or ".")
				if parsed is None:
					frappe.throw(_("nombre invalide ({0}).").format(text), frappe.ValidationError)
				values[fieldname] = int(parsed)
			elif field_type == "Check":
				values[fieldname] = parse_check(raw)
			elif field_type == "Link":
				df = meta.get_field(fieldname)
				link_doctype = df.options if df else ""
				if not link_doctype:
					frappe.throw(_("champ Link inconnu ({0}).").format(fieldname), frappe.ValidationError)
				values[fieldname] = _resolve_link(link_doctype, col.link_lookup_field, text)
			elif field_type == "Select":
				df = meta.get_field(fieldname)
				options = [option.strip() for option in cstr(df.options).split("\n") if option.strip()] if df else []
				if options and text not in options:
					frappe.throw(
						_("valeur {0} hors des options autorisees ({1}).").format(text, ", ".join(options[:8])),
						frappe.ValidationError,
					)
				values[fieldname] = text
			else:
				values[fieldname] = text
		except frappe.ValidationError as error:
			errors.append(f"{header}: {error}")

	if errors:
		return None, errors
	return values, []


def validate_rows(rows: list[dict], config, doctype: str) -> tuple[list[dict], list[str]]:
	"""All rows coerced + validated. Returns (valid_rows, error_messages);
	each valid row keeps its "_row" number and the match_on value under
	"_match"."""
	meta = frappe.get_meta(doctype)
	valid: list[dict] = []
	errors: list[str] = []
	seen_keys: dict[str, int] = {}
	match_on = config.match_on or ""
	duplicate_policy = config.on_duplicate or "Skip"
	for row in rows:
		row_number = row.get("_row")
		values, row_errors = coerce_row(row, config, meta)
		for message in row_errors:
			errors.append(_("Ligne {0}: {1}").format(row_number, message))
		if row_errors:
			continue
		if match_on:
			key_value = norm_text(values.get(match_on) or "")
			if not key_value:
				errors.append(_("Ligne {0}: colonne cle {1} vide.").format(row_number, match_on))
				continue
			values["_match"] = key_value
			if duplicate_policy == "Error" and key_value in seen_keys:
				errors.append(
					_("Ligne {0}: la cle {1} ({2}) apparait deja (ligne {3}).").format(
						row_number, match_on, key_value, seen_keys[key_value]
					)
				)
				continue
			seen_keys.setdefault(key_value, row_number)
		values["_row"] = row_number
		valid.append(values)
	return valid, errors


def validate_file(file_url: str, target: str) -> dict:
	"""The shared dry run behind the whitelisted endpoints: everything is
	read, coerced and checked; nothing is written. Header problems raise
	(nothing sensible to preview); row errors come back for the dialog and
	refuse import_records."""
	doctype = _doctype_for_target(target)
	_check_can_import(doctype)
	if not (file_url or "").lower().endswith(".xlsx"):
		frappe.throw(_("Le fichier doit etre un classeur .xlsx."), title=_("Fichier invalide"))
	config = get_import_config(target)
	raw_rows, problems = read_workbook_rows(file_url, config)
	if problems:
		frappe.throw(" ".join(problems), title=_("Import {0}").format(target))
	valid_rows, errors = validate_rows(raw_rows, config, doctype)
	return {"config": config, "doctype": doctype, "rows": valid_rows, "errors": errors}


# ── whitelisted endpoints ────────────────────────────────────────────────────


def _doctype_for_target(target: str) -> str:
	if target in SPECIALIZED_TARGETS:
		frappe.throw(
			_("{0} est importe par son propre flux (Grand Livre / plan comptable); le hub ne le gere pas.").format(target),
			title=_("Import"),
		)
	doctype = GENERIC_TARGETS.get(target)
	if not doctype:
		frappe.throw(_("Cible d'import inconnue: {0}.").format(target), frappe.ValidationError)
	return doctype


@frappe.whitelist()
def validate(file_url: str, target: str) -> dict:
	"""Dry run for the dialog: per-row validation errors, counts and a
	preview of the coerced rows. Nothing is written."""
	result = validate_file(file_url, target)
	rows = result["rows"]
	errors = result["errors"]
	return {
		"target": target,
		"doctype": result["doctype"],
		"row_count": len(rows),
		"columns": [col.target_field for col in result["config"].columns or []],
		"preview": [{key: cstr(value) for key, value in row.items() if not key.startswith("_")} for row in rows[:MAX_PREVIEW_ROWS]],
		"error_count": len(errors),
		"errors": errors[:MAX_PREVIEW_ERRORS],
		"ok": 0 if errors else 1,
	}


@frappe.whitelist()
def import_records(file_url: str, target: str) -> dict:
	"""Validate then upsert, all or nothing: any validation error refuses the
	run (the dialog shows them via validate); a failure during the writes
	rolls the whole run back (Error Log). match_on + on_duplicate come from
	the configuration."""
	try:
		result = validate_file(file_url, target)
		if result["errors"]:
			frappe.throw(
				_("{0} ligne(s) invalide(s): {1}").format(
					len(result["errors"]), " ".join(result["errors"][:MAX_PREVIEW_ERRORS])
				),
				title=_("Import {0}").format(target),
			)
		config = result["config"]
		doctype = result["doctype"]
		inserted = updated = skipped = 0
		names = []
		for row in result["rows"]:
			fields = {key: value for key, value in row.items() if not key.startswith("_")}
			action, name = _upsert_row(doctype, config, fields, row.get("_match"))
			if action == "inserted":
				inserted += 1
				names.append(name)
			elif action == "updated":
				updated += 1
			else:
				skipped += 1
		frappe.db.commit()
		return {"inserted": inserted, "updated": updated, "skipped": skipped, "names": names[:MAX_PREVIEW_ROWS]}
	except frappe.ValidationError:
		frappe.db.rollback()
		raise
	except Exception:
		frappe.db.rollback()
		frappe.log_error("axeane import hub failed", frappe.get_traceback())
		frappe.throw(
			_("Une erreur inattendue a interrompu l'import (voir Error Log)."), title=_("Import {0}").format(target)
		)


def _upsert_row(doctype: str, config, values: dict, match_value: str | None) -> tuple[str, str | None]:
	"""One row against the database: find the existing document by match_on
	and apply on_duplicate (Skip / Update / Error), else insert."""
	match_field = config.match_on
	on_duplicate = config.on_duplicate or "Skip"
	existing_name = None
	if match_field and match_value:
		existing_name = frappe.db.get_value(doctype, {match_field: match_value}, "name")
	if existing_name:
		if on_duplicate == "Skip":
			return ("skipped", existing_name)
		if on_duplicate == "Error":
			frappe.throw(_("{0} {1} existe deja.").format(_(match_field), match_value), frappe.ValidationError)
		doc = frappe.get_doc(doctype, existing_name)
		doc.update(values)
		doc.save()
		return ("updated", doc.name)
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert()
	return ("inserted", doc.name)


@frappe.whitelist()
def template(target: str) -> dict:
	"""A generated xlsx model: the configured headers (first alias of each
	column) on the configured header row, saved as a private File."""
	config = get_import_config(target)
	from openpyxl import Workbook

	wb = Workbook()
	ws = wb.active
	ws.title = (config.sheet_name or "Import")[:31]
	headers = [split_headers(col.xlsx_header)[0] if split_headers(col.xlsx_header) else col.target_field for col in config.columns or []]
	for _ in range(max(cint(config.header_row) - 1, 0)):
		ws.append([])
	ws.append(headers)
	stream = io.BytesIO()
	wb.save(stream)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"modele-import-{header_key(target).replace(' ', '-')}.xlsx",
			"is_private": 1,
			"content": stream.getvalue(),
		}
	).insert(ignore_permissions=True)
	return {"file_url": file_doc.file_url}
