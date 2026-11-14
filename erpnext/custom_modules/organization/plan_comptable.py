# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Import d'un plan comptable par entreprise depuis un fichier xlsx.

Chaque feuille du classeur décrit une classe de comptes (les noms des feuilles
sont ignorés) avec l'en-tête: Code | Libelle | Nature | Sens — Nature vaut
"Regroupement" ou "Comptable", sens vaut C, D ou DC. La classe d'un compte est
le premier chiffre de son code.

Les comptes déjà présents pour l'entreprise ne sont jamais modifiés ni
supprimés; seuls les codes absents sont insérés (name "<code> - <entreprise>").
Les helpers purs (parse_plan_workbook, classify_standard, resolve_parent) ne
dépendent pas de frappe et sont testables en python seul."""

import io
import re
import unicodedata
from collections import Counter

import frappe
from frappe import _
from frappe.utils import now_datetime
from frappe.utils.nestedset import rebuild_tree
from openpyxl import load_workbook

from erpnext.custom_modules.organization.context import _accessible_entreprises

MAX_LABEL_LENGTH = 140
# commit every ~200 inserts so transactions stay bounded on ~900 accounts
INSERT_CHUNK = 200
ERROR_PREVIEW = 50

HEADER_FIELDS = {"code", "libelle", "nature", "sens"}
NATURES = {"regroupement", "comptable"}
SENS_VALUES = {"C", "D", "DC"}


# ── pure helpers (no frappe) ──────────────────────────────────────────────────
def _as_text(value) -> str:
	"""Cell value -> clean text: xlsx numbers become plain strings ("101000"),
	whitespace at the ends is stripped."""
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return str(value).strip()


def _header_key(value) -> str:
	"""Case- and accent-insensitive header key ("Libellé" -> "libelle")."""
	text = _as_text(value).lower()
	return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _header_map(values) -> dict | None:
	"""Column indexes for the expected header row, or None when the row is not
	the header ("Code | Libelle | Nature | Sens" in any order)."""
	columns = {}
	for index, value in enumerate(values):
		key = _header_key(value)
		if key in HEADER_FIELDS and key not in columns:
			columns[key] = index
	return columns if len(columns) == len(HEADER_FIELDS) else None


def _normalize_label(value: str) -> str:
	"""Collapse doubled apostrophes ("d''exploitation" -> "d'exploitation")."""
	while "''" in value:
		value = value.replace("''", "'")
	return value


def parse_plan_workbook(content: bytes):
	"""Parse an xlsx plan comptable workbook.

	Returns (rows, errors):

	- rows: [{sheet, row, code, libelle, nature, sens, classe, is_group,
	  valid}] — EVERY non-empty data row of the file, in file order; `valid`
	  says whether the row can be imported, and rows with an invalid nature
	  carry is_group = None;
	- errors: [{sheet, row, code, message}] — one entry per problem found
	  (bad value, too long label, duplicate code, missing header...).

	Sheets are per class but their names vary and are irrelevant: the class is
	the first digit of the Code. Empty rows are skipped."""
	rows: list[dict] = []
	errors: list[dict] = []
	seen: dict[str, tuple] = {}  # code -> (sheet, row) already declared in the file
	workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	try:
		for sheet in workbook.worksheets:
			sheet_name = sheet.title
			header_map = None
			for row_number, cells in enumerate(sheet.iter_rows(values_only=True), start=1):
				if header_map is None:
					# preamble rows are consumed while looking for the header
					header_map = _header_map([_as_text(cell) for cell in cells])
					continue

				code = re.sub(r"\s+", "", _as_text(_cell(cells, header_map["code"])))
				libelle = _normalize_label(_as_text(_cell(cells, header_map["libelle"])))
				nature_raw = _as_text(_cell(cells, header_map["nature"]))
				sens_raw = _as_text(_cell(cells, header_map["sens"]))

				if not code and not libelle and not nature_raw and not sens_raw:
					continue  # empty row

				row_errors = []
				if not code:
					row_errors.append("Le code du compte est obligatoire.")
				elif not code.isdigit():
					row_errors.append(f"Le code {code} n'est pas valide: chiffres uniquement.")
				if not libelle:
					row_errors.append(f"Le libellé du compte {code or '?'} est obligatoire.")
				elif len(libelle) > MAX_LABEL_LENGTH:
					row_errors.append(f"Le libellé du compte {code} dépasse {MAX_LABEL_LENGTH} caractères.")
				nature = nature_raw.lower()
				if nature not in NATURES:
					row_errors.append(
						f"La nature du compte {code or '?'} doit être Regroupement ou Comptable (reçu: {nature_raw or 'vide'})."
					)
				sens = sens_raw.upper()
				if sens not in SENS_VALUES:
					row_errors.append(f"Le sens du compte {code or '?'} doit être C, D ou DC (reçu: {sens_raw or 'vide'}).")

				if code.isdigit():
					if code in seen:
						row_errors.append(
							f"Le code {code} apparaît déjà (feuille {seen[code][0]}, ligne {seen[code][1]})."
						)
					else:
						seen[code] = (sheet_name, row_number)
				else:
					code = code or None

				for message in row_errors:
					errors.append({"sheet": sheet_name, "row": row_number, "code": code, "message": message})
				rows.append(
					{
						"sheet": sheet_name,
						"row": row_number,
						"code": code,
						"libelle": libelle,
						"nature": "Regroupement" if nature == "regroupement" else ("Comptable" if nature == "comptable" else nature_raw or None),
						"sens": sens if sens in SENS_VALUES else None,
						"classe": code[:1] if code else None,
						"is_group": 1 if nature == "regroupement" else (0 if nature == "comptable" else None),
						"valid": not row_errors,
					}
				)
			if header_map is None:
				errors.append(
					{
						"sheet": sheet_name,
						"row": None,
						"code": None,
						"message": "En-tête Code | Libelle | Nature | Sens introuvable.",
					}
				)
	finally:
		workbook.close()
	return rows, errors


def classify_standard(is_group, sens) -> int:
	"""LOCK RULE — the single source of truth for is_standard, kept in ONE
	function so the rule can be changed later without touching anything else.

	1 (locked: cannot be edited or deleted) for every Regroupement and every
	Comptable whose normal balance (sens) is C (crédit) or D (débit) — that is
	every account of the imported plan comptable. 0 (editable) for a Comptable
	with sens DC (débit ou crédit). Locked accounts may still receive new
	sub-accounts."""
	if is_group:
		return 1
	return 0 if str(sens or "").strip().upper() == "DC" else 1


def resolve_parent(code: str, codes: dict) -> str | None:
	"""The parent of a code is the LONGEST PROPER PREFIX of the code that is
	present in `codes` as a Regroupement (codes maps account_number ->
	is_group, from the file and/or the database for the same entreprise).

	One-digit codes are the class roots and never have a parent; a 2+ digit
	code without any Regroupement prefix gets None (the caller treats that as
	an error row)."""
	if len(code) <= 1:
		return None
	for length in range(len(code) - 1, 0, -1):
		prefix = code[:length]
		if codes.get(prefix):
			return prefix
	return None


def _cell(cells, index):
	return cells[index] if index < len(cells) else None


# ── whitelisted entry point ───────────────────────────────────────────────────
@frappe.whitelist()
def import_plan_comptable(entreprise: str, file_url: str, dry_run: int = 0) -> dict:
	"""Importe le plan comptable xlsx d'une entreprise.

	dry_run=1: parse et contrôle seulement, rien n'est écrit. Retourne un
	résumé {ok, total, regroupements, comptables, standard, personnalises,
	par_classe, deja_existants, errors, error_count[, inserted]}."""
	try:
		return _import_plan_comptable(entreprise, file_url, dry_run)
	except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError):
		raise  # expected failures already carry their French message
	except Exception:
		frappe.db.rollback()
		frappe.log_error("axeane plan comptable import failed", frappe.get_traceback())
		frappe.throw(
			_("Une erreur inattendue a interrompu l'import du plan comptable (voir Error Log)."),
			title=_("Import plan comptable"),
		)


def _import_plan_comptable(entreprise: str, file_url: str, dry_run: int) -> dict:
	if not frappe.has_permission("Entreprise", "write", doc=entreprise):
		frappe.throw(_("Vous n'avez pas le droit de modifier cette entreprise."), frappe.PermissionError)
	if not frappe.has_permission("Chart of Account", "create"):
		frappe.throw(_("Vous n'avez pas le droit de créer des comptes."), frappe.PermissionError)
	if not frappe.db.exists("Entreprise", entreprise):
		frappe.throw(_("L'entreprise {0} n'existe pas.").format(entreprise), frappe.DoesNotExistError)
	if entreprise not in {row.name for row in _accessible_entreprises()}:
		frappe.throw(_("Vous n'avez pas acces a l'entreprise {0}.").format(entreprise), frappe.PermissionError)
	if not (file_url or "").lower().endswith(".xlsx"):
		frappe.throw(_("Le plan comptable doit être un fichier .xlsx."), title=_("Fichier invalide"))

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	rows, errors = parse_plan_workbook(file_doc.get_content())

	# accounts already stored for this entreprise: never overwritten, never
	# deleted — only codes absent from here get inserted
	db_rows = frappe.get_all(
		"Chart of Account",
		filters={"entreprise": entreprise},
		fields=["name", "account_number", "is_group"],
	)
	existing = {row.account_number: row.name for row in db_rows if row.account_number}
	# parent resolution sees the file's codes AND the database's (the
	# database wins for a code present in both: that row is kept as-is)
	codes = {row["code"]: row["is_group"] for row in rows if row["code"]}
	codes.update({row.account_number: (1 if row.is_group else 0) for row in db_rows if row.account_number})

	# parent of every code: longest proper Regroupement prefix in the file or
	# the database; a 2+ digit code without one is an error row
	parent_of = {}
	for row in rows:
		if not row["code"]:
			continue
		parent_code = resolve_parent(row["code"], codes)
		if parent_code:
			parent_of[row["code"]] = parent_code
		else:
			errors.append(
				{
					"sheet": row["sheet"],
					"row": row["row"],
					"code": row["code"],
					"message": f"Aucun parent (regroupement) trouvé pour le code {row['code']}.",
				}
			)

	# the summary describes the whole file; rows with an undecidable nature or
	# sens (reported in errors) can't take part in the nature/sens counts
	classifiable = [row for row in rows if row["is_group"] is not None and row["sens"] is not None]
	standard = sum(classify_standard(row["is_group"], row["sens"]) for row in classifiable)
	summary = {
		"ok": len(errors) == 0,
		"total": len(rows),
		"regroupements": sum(1 for row in rows if row["is_group"] == 1),
		"comptables": sum(1 for row in rows if row["is_group"] == 0),
		"standard": standard,
		"personnalises": sum(1 for row in classifiable if not classify_standard(row["is_group"], row["sens"])),
		"par_classe": dict(sorted(Counter(row["classe"] for row in rows if row["classe"]).items())),
		"deja_existants": len({row["code"] for row in rows if row["code"]} & set(existing)),
		"errors": errors[:ERROR_PREVIEW],
		"error_count": len(errors),
	}

	if dry_run:
		return summary
	if summary["error_count"] > 0:
		summary["ok"] = False
		return summary

	inserted = 0
	pending = 0
	# only clean rows are inserted, shortest codes first so every parent is
	# stored before its children; existing accounts are never touched
	insertable = [row for row in rows if row["valid"] and row["code"] not in existing]
	for row in sorted(insertable, key=lambda r: (len(r["code"]), r["code"])):
		parent_code = parent_of.get(row["code"])
		doc = frappe.new_doc("Chart of Account")
		doc.name = f"{row['code']} - {entreprise}"
		doc.update(
			{
				"account_number": row["code"],
				"account_name": row["libelle"],
				"is_group": row["is_group"],
				"sens": row["sens"],
				"classe": row["classe"],
				"entreprise": entreprise,
				# a parent already in the database keeps its real name (a
				# legacy row may predate the "<code> - <entreprise>" format)
				"parent_chart_of_account": existing.get(parent_code) or (f"{parent_code} - {entreprise}" if parent_code else None),
				"is_standard": classify_standard(row["is_group"], row["sens"]),
			}
		)
		doc.flags.is_standard_import = True
		doc.set_user_and_timestamp()
		doc.db_insert()
		inserted += 1
		pending += 1
		if pending >= INSERT_CHUNK:
			frappe.db.commit()
			pending = 0

	# one single nested-set rebuild for the whole doctype (handles the forest
	# of every entreprise's rows; per-row doc.insert() would update ~900 nodes)
	rebuild_tree("Chart of Account")
	frappe.db.set_value(
		"Entreprise",
		entreprise,
		{"plan_comptable_fichier": file_url, "plan_comptable_ajoute_le": now_datetime()},
	)
	frappe.db.commit()
	summary["inserted"] = inserted
	return summary
