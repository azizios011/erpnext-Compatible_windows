# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Import Axeane's "Grand Livre" xlsx into the Ecriture Comptable ledger.

The workbook has one sheet with the header Date | Mvt | Compte | Libellé |
Journal | Pièce | Débit | Crédit | Solde | Lettage. The import is validated
end to end (dry run via validate_grand_livre), all or nothing, and written
with frappe.db.bulk_insert: every inserted row carries an import_batch so
replace / delete can find them without ever touching the rows posted by
entries. The workbook is read with openpyxl in read_only mode (the real
Grand Livre file has no default column style and hangs openpyxl's normal
mode) and every cell is normalized like the UI sees it.

Every entry point requires the Accounts Manager or System Manager role and
the strict accounting context (require_context); the writes also require an
Ouvert Exercice (validate_exercice_open).
"""

import io
import re
import unicodedata
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, now_datetime

from erpnext.custom_modules.organization.context import require_context, validate_exercice_open
from erpnext.custom_modules.reports.imported_entries import delete_imported_entries, flagged_linked_rows

LEDGER_DOCTYPE = "Ecriture Comptable"
IMPORT_ROLES = ("Accounts Manager", "System Manager")
TOTAL_TOLERANCE = 0.001
MAX_LISTED_ACCOUNTS = 50
MAX_LISTED_ROWS = 20

# the sheet's header cells, matched accent/case-insensitively; Solde and
# Lettage exist in the file but are not imported
HEADER_ALIASES = {
	"date": "date",
	"mvt": "mvt",
	"compte": "compte",
	"libelle": "libelle",
	"journal": "journal",
	"piece": "piece",
	"debit": "debit",
	"credit": "credit",
	"solde": "solde",
	"letrage": "lettrage",  # the source file spells the column "Letrage"
	"letage": "lettrage",
	"lettrage": "lettrage",
}
REQUIRED_HEADERS = ("date", "mvt", "compte", "journal", "debit", "credit")

JOURNAL_TYPE_BY_CODE = {
	"AC": "Achat",
	"VT": "Vente",
	"BQ": "Banque",
	"BTK": "Banque",
	"ATB": "Banque",
}
DEFAULT_JOURNAL_TYPE = "Operations Diverses"


def _check_import_roles() -> None:
	roles = frappe.get_roles(frappe.session.user)
	if not (IMPORT_ROLES[0] in roles or IMPORT_ROLES[1] in roles):
		frappe.throw(_("Not permitted to import the Grand Livre"), frappe.PermissionError)


def _header_key(value) -> str:
	"""Header cell → the accent-free lowercase key the aliases map on."""
	text = cstr(value).strip().lower()
	return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _norm_text(value) -> str:
	"""Text cells: stripped; an integral float loses the trailing .0 (the
	Compte 401000.0 becomes "401000", a text Mvt keeps its leading zeros)."""
	if value is None:
		return ""
	if isinstance(value, float) and value.is_integer():
		return str(int(value))
	return cstr(value).strip()


def _parse_date(value):
	"""A real date cell or a valid "dd/mm/yyyy" text, else None (invalid)."""
	if value is None:
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = str(value).strip()
	match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
	if match:
		try:
			return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
		except ValueError:
			return None  # "31/13/2026" and friends: reported as date invalide
	return None


def _cell(cells: tuple, index: int):
	return cells[index] if index < len(cells) else None


def _file_content(file_url: str) -> bytes:
	if not file_url:
		frappe.throw(_("A file is required."), frappe.ValidationError)
	file = frappe.get_doc("File", {"file_url": file_url})
	return file.get_content()


def _read_rows(file_url: str) -> tuple[list[dict], list[str], int, int]:
	"""Read and normalize the Grand Livre sheet.

	Returns (rows, row_problems, zero_skipped, lettrage_ignored): the
	normalized data rows (a row with a problem is never returned), the
	per-row blocker messages, and the counts of the rows ignored for having
	both amounts empty and of the ignored Lettage values.
	"""
	from openpyxl import load_workbook

	content = _file_content(file_url)
	workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
	rows: list[dict] = []
	problems: list[str] = []
	zero_skipped = 0
	lettrage_ignored = 0
	try:
		sheet = workbook.worksheets[0]
		columns = None
		for row_number, cells in enumerate(sheet.iter_rows(values_only=True), start=1):
			if columns is None:
				# the header row is detected by name, tolerant of a preamble
				# row above it, of extra columns and of the column order
				mapped: dict[str, int] = {}
				for index, cell in enumerate(cells):
					key = HEADER_ALIASES.get(_header_key(cell))
					if key and key not in mapped:
						mapped[key] = index
				if all(header in mapped for header in REQUIRED_HEADERS):
					columns = mapped
				continue

			journal = _norm_text(_cell(cells, columns["journal"]))
			mvt = _norm_text(_cell(cells, columns["mvt"]))
			compte = _norm_text(_cell(cells, columns["compte"]))
			date_value = _parse_date(_cell(cells, columns["date"]))
			if date_value is None and not journal and not mvt and not compte:
				continue  # empty row

			if date_value is None:
				problems.append(_("Ligne {0}: date invalide.").format(row_number))
				continue
			if not journal:
				problems.append(_("Ligne {0}: journal manquant.").format(row_number))
				continue
			if not mvt:
				problems.append(_("Ligne {0}: MVT manquant.").format(row_number))
				continue
			if not compte:
				problems.append(_("Ligne {0}: compte manquant.").format(row_number))
				continue

			debit = flt(_cell(cells, columns["debit"]))
			credit = flt(_cell(cells, columns["credit"]))
			if debit < 0 or credit < 0:
				problems.append(_("Ligne {0}: montant negatif.").format(row_number))
				continue
			if debit > 0 and credit > 0:
				problems.append(_("Ligne {0}: debit et credit simultanes.").format(row_number))
				continue
			if debit == 0 and credit == 0:
				zero_skipped += 1
				continue

			lettrage_cell = _cell(cells, columns["lettrage"]) if "lettrage" in columns else None
			if _norm_text(lettrage_cell):
				lettrage_ignored += 1

			rows.append(
				{
					"row": row_number,
					"date": date_value,
					"journal": journal,
					"mvt": mvt,
					"compte": compte,
					"libelle": _norm_text(_cell(cells, columns["libelle"])) if "libelle" in columns else "",
					"ref_doc": _norm_text(_cell(cells, columns["piece"])) if "piece" in columns else "",
					"debit": flt(debit, 3),
					"credit": flt(credit, 3),
				}
			)
	finally:
		workbook.close()
	if columns is None:
		problems.append(
			_("En-tete invalide: les colonnes {0} sont attendues.").format(", ".join(REQUIRED_HEADERS))
		)
		return rows, problems, zero_skipped, lettrage_ignored
	return rows, problems, zero_skipped, lettrage_ignored


def _analyze(file_url: str, context: dict, create_journals: int) -> dict:
	"""All the data validation shared by the dry run and the import. The
	import-specific refusals (existing rows / replace) stay in import_grand_livre."""
	rows, row_problems, zero_skipped, lettrage_ignored = _read_rows(file_url)
	blockers: list[str] = list(row_problems)
	warnings: list[str] = []

	if row_problems:
		blockers.append(_("{0} ligne(s) du fichier sont invalides.").format(len(row_problems)))
	if zero_skipped:
		warnings.append(_("{0} ligne(s) ignoree(s): debit et credit vides.").format(zero_skipped))
	if lettrage_ignored:
		warnings.append(_("{0} valeur(s) Lettage ignoree(s): l'import ne lettre pas.").format(lettrage_ignored))

	total_debit = flt(sum(row["debit"] for row in rows), 3)
	total_credit = flt(sum(row["credit"] for row in rows), 3)
	if abs(total_debit - total_credit) > TOTAL_TOLERANCE:
		blockers.append(
			_("Le Grand Livre n'est pas equilibre: total debit {0} vs total credit {1}.").format(
				flt(total_debit, 3), flt(total_credit, 3)
			)
		)

	# the dates must fall inside the Exercice
	debut = getdate(context.get("date_debut")) if context.get("date_debut") else None
	fin = getdate(context.get("date_fin")) if context.get("date_fin") else None
	out_of_range = [
		{"row": row["row"], "date": row["date"].strftime("%d/%m/%Y")}
		for row in rows
		if (debut and row["date"] < debut) or (fin and row["date"] > fin)
	]
	if out_of_range:
		blockers.append(
			_("{0} date(s) hors de l'exercice {1} - {2}.").format(
				len(out_of_range), context.get("date_debut"), context.get("date_fin")
			)
		)

	# the missing accounts are never auto-created
	compte_numbers = {row["compte"] for row in rows}
	coa = frappe.get_all(
		"Chart of Account",
		filters={"entreprise": context["entreprise"], "account_number": ("in", sorted(compte_numbers))},
		fields=["name", "account_number"],
	)
	account_by_number = {row.account_number: row.name for row in coa}
	missing_numbers = compte_numbers - set(account_by_number)
	if missing_numbers:
		blockers.append(
			_("{0} compte(s) inconnu(s) dans le plan de l'entreprise (aucun compte cree): {1}.").format(
				len(missing_numbers), ", ".join(sorted(missing_numbers)[:10])
			)
		)

	# the missing journals are created on import (create_journals), globally
	journal_codes = {row["journal"] for row in rows}
	existing_journals = set(frappe.get_all("Journal", filters={"name": ("in", sorted(journal_codes))}, pluck="name"))
	missing_journals = sorted(journal_codes - existing_journals)
	if missing_journals and not cint(create_journals):
		blockers.append(
			_("Journaux manquants (activez Creer les journaux manquants): {0}.").format(", ".join(missing_journals))
		)

	# the (journal, mvt, date) groups are expected to balance — a warning,
	# the strict check stays the workbook-wide totals
	groups: dict[tuple, list[float]] = {}
	for row in rows:
		key = (row["journal"], row["mvt"], row["date"])
		sums = groups.setdefault(key, [0.0, 0.0])
		sums[0] = flt(sums[0] + row["debit"], 3)
		sums[1] = flt(sums[1] + row["credit"], 3)
	unbalanced = [key for key, (debit, credit) in groups.items() if abs(debit - credit) > TOTAL_TOLERANCE]
	if unbalanced:
		warnings.append(_("{0} groupe(s) (journal, mvt, date) non equilibre(s).").format(len(unbalanced)))
		for journal, mvt, group_date in unbalanced[:MAX_LISTED_ROWS]:
			sums = groups[(journal, mvt, group_date)]
			warnings.append(
				f"{journal} · {mvt} · {group_date.strftime('%d/%m/%Y')} : "
				+ _("debit {0} vs credit {1}").format(flt(sums[0], 3), flt(sums[1], 3))
			)

	# the rows already imported / posted in this context
	existing_import_rows = frappe.db.count(
		LEDGER_DOCTYPE,
		{
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"import_batch": ("is", "set"),
		},
	)
	entry_rows = frappe.db.count(
		LEDGER_DOCTYPE,
		{
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"import_batch": ("is", "not set"),
		},
	)
	if entry_rows:
		warnings.append(
			_("{0} ligne(s) du contexte viennent d'ecritures: elles ne sont pas touchees.").format(entry_rows)
		)

	row_dates = [row["date"] for row in rows]
	return {
		"rows": len(rows),
		"entries": len(groups),
		"accounts": len(compte_numbers),
		"journals": len(journal_codes),
		"date_min": min(row_dates).strftime("%Y-%m-%d") if row_dates else "",
		"date_max": max(row_dates).strftime("%Y-%m-%d") if row_dates else "",
		"total_debit": total_debit,
		"total_credit": total_credit,
		"missing_accounts": [
			{"number": number, "rows": sum(1 for row in rows if row["compte"] == number)}
			for number in sorted(missing_numbers)
		][:MAX_LISTED_ACCOUNTS],
		"missing_journals": missing_journals,
		"out_of_range": out_of_range[:MAX_LISTED_ROWS],
		"existing_import_rows": existing_import_rows,
		"blockers": blockers,
		"warnings": warnings,
		"zero_skipped": zero_skipped,
		"lettrage_ignored": lettrage_ignored,
		# internal: never shipped to the client
		"data": rows,
		"account_by_number": account_by_number,
	}


def _client_summary(analysis: dict) -> dict:
	"""The dry-run payload: everything but the internal keys."""
	return {key: value for key, value in analysis.items() if key not in ("data", "account_by_number")}


@frappe.whitelist()
def validate_grand_livre(file_url: str) -> dict:
	"""Dry run: read and validate the workbook, return the summary without
	writing anything. The import re-runs the whole validation itself."""
	_check_import_roles()
	context = require_context()
	return _client_summary(_analyze(file_url, context, create_journals=1))


@frappe.whitelist()
def import_grand_livre(file_url: str, replace: int = 0, create_journals: int = 1) -> dict:
	"""Import the workbook into the ledger, all or nothing.

	replace: delete this context's previous import first (refused when any of
	those rows is lettree or pointee). create_journals: create the missing
	Journal rows (global, name = the code). Entry-posted rows are untouched.
	"""
	_check_import_roles()
	context = require_context()
	validate_exercice_open(context)
	replace = cint(replace)
	create_journals = cint(create_journals)
	try:
		analysis = _analyze(file_url, context, create_journals)

		# the import-specific refusals, appended to the data blockers
		if analysis["existing_import_rows"] and not replace:
			analysis["blockers"].append(
				_("Le contexte contient deja {0} ligne(s) importee(s): activez Remplacer l'import precedent.").format(
					analysis["existing_import_rows"]
				)
			)
		if replace and analysis["existing_import_rows"]:
			flagged = _flagged_import_rows(context)
			if flagged:
				analysis["blockers"].append(
					_("L'import precedent contient {0} ligne(s) lettrees ou pointees: delettrer d'abord.").format(
						len(flagged)
					)
				)
		if analysis["blockers"]:
			frappe.throw(
				_("Import impossible: {0}").format(" ".join(analysis["blockers"])),
				title=_("Import Grand Livre"),
			)

		# replace: drop the previous import (only the import_batch rows) AND
		# the entries materialized from it, so nothing is left behind
		replaced = 0
		entries_deleted = 0
		if replace and analysis["existing_import_rows"]:
			imported_names = frappe.get_all(
				LEDGER_DOCTYPE,
				filters={
					"entreprise": context["entreprise"],
					"exercice": context["exercice"],
					"import_batch": ("is", "set"),
				},
				pluck="name",
			)
			frappe.db.delete(LEDGER_DOCTYPE, {"name": ("in", imported_names)})
			entries_deleted = delete_imported_entries(context)
			replaced = len(imported_names)

		# the missing journals, created globally (name = the code)
		journals_created = []
		for code in analysis["missing_journals"]:
			frappe.get_doc(
				{
					"doctype": "Journal",
					"journal_code": code,
					"journal_name": code,
					"journal_type": JOURNAL_TYPE_BY_CODE.get(code, DEFAULT_JOURNAL_TYPE),
				}
			).insert(ignore_permissions=True)
			journals_created.append(code)

		now = now_datetime()
		batch = f"GL-{now.strftime('%Y%m%d-%H%M%S')}-{frappe.session.user}"
		fields = [
			"name",
			"creation",
			"modified",
			"modified_by",
			"owner",
			"docstatus",
			"idx",
			"posting_date",
			"mois",
			"annee",
			"journal",
			"mvt",
			"account",
			"libelle",
			"debit",
			"credit",
			"ref_doc",
			"entreprise",
			"exercice",
			"devise",
			"tresorerie",
			"lettrage",
			"lettrage_status",
			"pointe",
			"source_entry_doctype",
			"source_entry",
			"source_doctype",
			"source_name",
			"import_batch",
		]
		user = frappe.session.user
		values = []
		for index, row in enumerate(analysis["data"], start=1):
			values.append(
				(
					frappe.generate_hash(length=10),
					now,
					now,
					user,
					user,
					0,
					index,
					row["date"],
					row["date"].month,
					row["date"].year,
					row["journal"],
					row["mvt"],
					analysis["account_by_number"][row["compte"]],
					row["libelle"],
					row["debit"],
					row["credit"],
					row["ref_doc"],
					context["entreprise"],
					context["exercice"],
					"TND",
					"",
					"",
					"Non lettre",
					0,
					"",
					"",
					"",
					"",
					batch,
				)
			)
		frappe.db.bulk_insert(LEDGER_DOCTYPE, fields=fields, values=values, chunk_size=1000)
		if values:
			# every imported movement becomes a real Entry (materialized as
			# already posted, no new ledger rows): the run is a background job
			# after the import's own commit
			frappe.enqueue(
				"erpnext.custom_modules.reports.imported_entries.materialize_imported_entries_job",
				queue="long",
				timeout=3600,
				job_id=f"gl_materialize_{context['entreprise']}_{context['exercice']}",
				deduplicate=True,
				enqueue_after_commit=True,
			)
		return {
			"inserted": len(values),
			"entries": analysis["entries"],
			"batch": batch,
			"journals_created": journals_created,
			"replaced": replaced,
			"entries_deleted": entries_deleted,
			"materialize_enqueued": 1 if values else 0,
		}
	except frappe.exceptions.ValidationError:
		# the expected refusals: re-raised as-is, nothing to roll back yet
		raise
	except Exception:
		frappe.db.rollback()
		frappe.log_error("Axeane Grand Livre import failed", frappe.get_traceback())
		frappe.throw(_("L'import du Grand Livre a echoue (voir Error Log)."), title=_("Import Grand Livre"))


@frappe.whitelist()
def delete_import() -> dict:
	"""Delete this context's imported rows (import_batch set) AND the entries
	materialized from them (only those flagged imported), including the rows a
	re-save re-posted. Refused while any of them is lettree or pointee."""
	_check_import_roles()
	context = require_context()
	validate_exercice_open(context)
	imported_names = frappe.get_all(
		LEDGER_DOCTYPE,
		filters={
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"import_batch": ("is", "set"),
		},
		pluck="name",
	)
	flagged = _flagged_import_rows(context)
	if flagged:
		frappe.throw(
			_("Impossible de supprimer: {0} ligne(s) lettrees ou pointees (delettrer d'abord).").format(len(flagged)),
			title=_("Supprimer l'import"),
		)
	if not imported_names:
		return {"deleted": 0, "entries_deleted": 0}
	frappe.db.delete(LEDGER_DOCTYPE, {"name": ("in", imported_names)})
	entries_deleted = delete_imported_entries(context)
	return {"deleted": len(imported_names), "entries_deleted": entries_deleted}


def _flagged_import_rows(context: dict) -> list[str]:
	"""The imported rows of this context that are lettree or pointee: the
	import_batch rows, plus the rows a re-save of an imported entry re-posted
	(no import_batch anymore, but still linked to a materialized entry)."""
	flagged = frappe.get_all(
		LEDGER_DOCTYPE,
		filters={
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"import_batch": ("is", "set"),
		},
		or_filters=[
			[LEDGER_DOCTYPE, "lettrage_status", "!=", "Non lettre"],
			[LEDGER_DOCTYPE, "pointe", "=", 1],
		],
		pluck="name",
	)
	linked = [name for name in flagged_linked_rows(context) if name not in flagged]
	return flagged + linked
