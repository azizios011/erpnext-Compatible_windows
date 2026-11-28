# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Server-side API for the Suppression des Ecritures screen.

Provides whitelisted methods:

- **search_transactions**: paginated search over the four entry doctypes +
  legacy ledger rows with no entry, scoped to the dock context.
- **count_transactions**: counts matching transactions per entry type + lettered.
- **delete_transactions**: bulk-delete entries (or legacy ledger groups) and
  their ledger rows with chunk-commits and progress, skipping (or force-clearing)
  lettered / pointed rows.

All queries are scoped to the current Entreprise + Exercice
(require_context). The Exercice must be Ouvert for deletions
(validate_exercice_open). Only Accounts Manager / System Manager may use
this module.
"""

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

from erpnext.custom_modules.entries.ledger_lock import locked_row_names
from erpnext.custom_modules.organization.context import (
	require_context,
	validate_exercice_open,
)
from erpnext.custom_modules.reports.imported_entries import (
	delete_imported_entries,
	flagged_linked_rows,
)

LEDGER_DOCTYPE = "Ecriture Comptable"
CHILD_DOCTYPE = "Ecriture Ligne"
DECLARATION_LINE_DOCTYPE = "Declaration Transaction Rubrique"

ENTRY_DOCTYPES = (
	"Payable Transaction",
	"Receivable Transaction",
	"Treasury Transaction",
	"Declaration Transaction",
)

ENTRY_DOCTYPE_LABELS: dict[str, str] = {
	"Payable Transaction": "Payable",
	"Receivable Transaction": "Receivable",
	"Treasury Transaction": "Treasury",
	"Declaration Transaction": "Declaration",
	LEDGER_DOCTYPE: "Sans écriture",
}

CHUNK_SIZE = 200


# ── helpers ──────────────────────────────────────────────────────────────────


def _check_roles() -> None:
	roles = set(frappe.get_roles())
	if not (roles & {"Accounts Manager", "System Manager"}):
		frappe.throw(_("Accès réservé aux Accounts Manager / System Manager."), frappe.PermissionError)


def _parse_filters(raw: str | dict | None) -> dict[str, Any]:
	if not raw:
		return {}
	if isinstance(raw, str):
		return json.loads(raw)
	return dict(raw)


def _parse_journals(raw: Any) -> list[str]:
	if not raw:
		return []
	if isinstance(raw, str):
		return [j.strip() for j in raw.replace("[", "").replace("]", "").replace('"', "").split(",") if j.strip()]
	return [str(j).strip() for j in raw if str(j).strip()]


def _build_entry_where(
	dt: str,
	filters: dict[str, Any],
	context: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
	"""Build WHERE clause fragments for one of the 4 entry doctypes."""
	if dt == "Declaration Transaction":
		return _build_declaration_where(filters, context)
	clauses: list[str] = [
		"e.entreprise = %(entreprise)s",
		"e.exercice = %(exercice)s",
	]
	params: dict[str, Any] = {
		"entreprise": context["entreprise"],
		"exercice": context["exercice"],
		"parenttype": dt,
	}

	journals = _parse_journals(filters.get("journal"))
	if journals:
		placeholders = ", ".join(f"%(j{i})s" for i in range(len(journals)))
		clauses.append(f"e.journal IN ({placeholders})")
		for i, j in enumerate(journals):
			params[f"j{i}"] = j

	if filters.get("mvt"):
		clauses.append("e.mvt LIKE %(mvt)s")
		params["mvt"] = f"%{filters['mvt']}%"

	if filters.get("ref_doc"):
		clauses.append("e.ref_doc LIKE %(ref_doc)s")
		params["ref_doc"] = f"%{filters['ref_doc']}%"

	if filters.get("date_from"):
		clauses.append("e.date_operation >= %(date_from)s")
		params["date_from"] = filters["date_from"]

	if filters.get("date_to"):
		clauses.append("e.date_operation <= %(date_to)s")
		params["date_to"] = filters["date_to"]

	if filters.get("libelle"):
		clauses.append(
			f"""(e.libelle LIKE %(libelle)s OR EXISTS (
				SELECT 1 FROM `tab{CHILD_DOCTYPE}` l
				WHERE l.parenttype = %(parenttype)s AND l.parent = e.name AND l.libelle LIKE %(libelle)s
			))"""
		)
		params["libelle"] = f"%{filters['libelle']}%"

	if filters.get("compte"):
		clauses.append(
			f"""EXISTS (
				SELECT 1 FROM `tab{CHILD_DOCTYPE}` l
				WHERE l.parenttype = %(parenttype)s AND l.parent = e.name AND l.account LIKE %(compte)s
			)"""
		)
		params["compte"] = f"%{filters['compte']}%"

	origin = filters.get("origin")
	if dt in ("Payable Transaction", "Receivable Transaction", "Treasury Transaction"):
		if origin == "Imported":
			clauses.append("e.imported = 1")
		elif origin == "Saisie":
			clauses.append("(e.imported = 0 OR e.imported IS NULL)")
	elif origin == "Imported":
		clauses.append("1 = 0")

	return " AND ".join(clauses), params


def _build_declaration_where(
	filters: dict[str, Any],
	context: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
	"""The Declaration Transaction columns are the DM redesign's (mois, type,
	status, numero_recepisse) — no journal / mvt / posting_date: the shared
	entry filters map onto them, the rest are ignored."""
	clauses: list[str] = [
		"e.entreprise = %(entreprise)s",
		"e.exercice = %(exercice)s",
	]
	params: dict[str, Any] = {
		"entreprise": context["entreprise"],
		"exercice": context["exercice"],
	}

	if filters.get("mvt"):
		clauses.append("e.name LIKE %(mvt)s")
		params["mvt"] = f"%{filters['mvt']}%"

	if filters.get("ref_doc"):
		clauses.append("e.numero_recepisse LIKE %(ref_doc)s")
		params["ref_doc"] = f"%{filters['ref_doc']}%"

	if filters.get("libelle"):
		clauses.append("e.type_declaration LIKE %(libelle)s")
		params["libelle"] = f"%{filters['libelle']}%"

	return " AND ".join(clauses), params


def _build_legacy_where(
	filters: dict[str, Any],
	context: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
	"""Build WHERE and HAVING clauses for legacy ledger rows (no source_entry)."""
	clauses: list[str] = [
		"ec.entreprise = %(entreprise)s",
		"ec.exercice = %(exercice)s",
		"(ec.source_entry IS NULL OR ec.source_entry = '')",
	]
	having_clauses: list[str] = []
	params: dict[str, Any] = {
		"entreprise": context["entreprise"],
		"exercice": context["exercice"],
	}

	journals = _parse_journals(filters.get("journal"))
	if journals:
		placeholders = ", ".join(f"%(j{i})s" for i in range(len(journals)))
		clauses.append(f"ec.journal IN ({placeholders})")
		for i, j in enumerate(journals):
			params[f"j{i}"] = j

	if filters.get("mvt"):
		clauses.append("ec.mvt LIKE %(mvt)s")
		params["mvt"] = f"%{filters['mvt']}%"

	if filters.get("ref_doc"):
		clauses.append("ec.ref_doc LIKE %(ref_doc)s")
		params["ref_doc"] = f"%{filters['ref_doc']}%"

	if filters.get("date_from"):
		clauses.append("ec.posting_date >= %(date_from)s")
		params["date_from"] = filters["date_from"]

	if filters.get("date_to"):
		clauses.append("ec.posting_date <= %(date_to)s")
		params["date_to"] = filters["date_to"]

	if filters.get("libelle"):
		having_clauses.append("MAX(CASE WHEN ec.libelle LIKE %(libelle)s THEN 1 ELSE 0 END) = 1")
		params["libelle"] = f"%{filters['libelle']}%"

	if filters.get("compte"):
		having_clauses.append("MAX(CASE WHEN ec.account LIKE %(compte)s THEN 1 ELSE 0 END) = 1")
		params["compte"] = f"%{filters['compte']}%"

	origin = filters.get("origin")
	if origin == "Imported":
		clauses.append("(ec.import_batch IS NOT NULL AND ec.import_batch != '')")
	elif origin == "Saisie":
		clauses.append("(ec.import_batch IS NULL OR ec.import_batch = '')")

	where_sql = " AND ".join(clauses)
	having_sql = ("HAVING " + " AND ".join(having_clauses)) if having_clauses else ""
	return where_sql, having_sql, params


def _entry_type_doctypes(entry_type: str | None) -> tuple[str, ...]:
	"""Resolve the user-facing entry_type filter to a tuple of doctypes."""
	mapping = {
		"Payable": ("Payable Transaction",),
		"Receivable": ("Receivable Transaction",),
		"Treasury": ("Treasury Transaction",),
		"Declaration": ("Declaration Transaction",),
	}
	if entry_type and entry_type in mapping:
		return mapping[entry_type]
	return ENTRY_DOCTYPES


def _include_legacy(entry_type: str | None) -> bool:
	return not entry_type


def _prefix_sql(sql: str, params: dict[str, Any], prefix: str) -> tuple[str, dict[str, Any]]:
	prefixed_params = {f"{prefix}{k}": v for k, v in params.items()}
	prefixed_sql = sql
	for k in params:
		prefixed_sql = prefixed_sql.replace(f"%({k})s", f"%({prefix}{k})s")
	return prefixed_sql, prefixed_params


# ── search ───────────────────────────────────────────────────────────────────


@frappe.whitelist()
def search_transactions(
	filters: str | dict | None = None,
	page: int = 1,
	page_size: int = 20,
) -> dict[str, Any]:
	"""Paginated search over entries (and legacy ledger rows with no entry)
	in the dock context.

	Returns ``{"rows": [...], "total": N, "page": P, "page_size": S}``.
	"""
	_check_roles()
	context = require_context()
	f = _parse_filters(filters)
	doctypes = _entry_type_doctypes(f.get("entry_type"))
	include_legacy = _include_legacy(f.get("entry_type"))

	page = max(1, cint(page))
	page_size = min(100, max(1, cint(page_size)))
	offset = (page - 1) * page_size

	total = 0
	union_parts: list[str] = []
	all_params: dict[str, Any] = {}

	for idx, dt in enumerate(doctypes):
		where_sql, params = _build_entry_where(dt, f, context)
		total += cint(frappe.db.sql(f"SELECT COUNT(*) FROM `tab{dt}` e WHERE {where_sql}", params)[0][0])

		has_imported = dt in ("Payable Transaction", "Receivable Transaction", "Treasury Transaction")
		imported_expr = "e.imported" if has_imported else "0"
		p_where, p_params = _prefix_sql(where_sql, params, f"p{idx}_")

		lettered_sub = f"""(SELECT COUNT(*) FROM `tab{LEDGER_DOCTYPE}` ec
			WHERE ec.source_entry_doctype = '{dt}'
			  AND ec.source_entry = e.name
			  AND (ec.lettrage_status != 'Non lettre' OR ec.pointe = 1)) > 0"""

		if dt == "Declaration Transaction":
			# the DM redesign's columns mapped onto the shared row shape:
			# mois in the Mvt slot, the type in Journal, the status in
			# Libelle, the receipisse in Ref and the grand total once
			select_columns = (
				"e.mois AS mvt, e.type_declaration AS journal, e.depose_le AS date_operation, "
				"e.status AS libelle, e.numero_recepisse AS ref_doc, "
				"e.total_a_payer AS total_debit, 0 AS total_credit"
			)
		else:
			select_columns = (
				"e.mvt, e.journal, e.date_operation, e.libelle, e.ref_doc, "
				"e.total_debit, e.total_credit"
			)

		union_parts.append(f"""
			SELECT e.name, '{dt}' AS doctype,
				   {select_columns},
				   '{ENTRY_DOCTYPE_LABELS.get(dt, dt)}' AS entry_type,
				   {imported_expr} AS imported,
				   ({lettered_sub}) AS has_lettered
			FROM `tab{dt}` e
			WHERE {p_where}
		""")
		all_params.update(p_params)

	if include_legacy:
		l_where, l_having, l_params = _build_legacy_where(f, context)
		legacy_count_sql = f"""
			SELECT COUNT(*) FROM (
				SELECT ec.journal, ec.mvt
				FROM `tab{LEDGER_DOCTYPE}` ec
				WHERE {l_where}
				GROUP BY COALESCE(ec.journal, ''), COALESCE(ec.mvt, '')
				{l_having}
			) legacy_groups
		"""
		total += cint(frappe.db.sql(legacy_count_sql, l_params)[0][0])

		p_l_where, p_l_params = _prefix_sql(l_where, l_params, "leg_")
		p_l_having, _ = _prefix_sql(l_having, l_params, "leg_")
		union_parts.append(f"""
			SELECT CONCAT(COALESCE(ec.journal, ''), '::', COALESCE(ec.mvt, '')) AS name,
				   '{LEDGER_DOCTYPE}' AS doctype,
				   COALESCE(ec.mvt, '') AS mvt,
				   COALESCE(ec.journal, '') AS journal,
				   MIN(ec.posting_date) AS date_operation,
				   MAX(ec.libelle) AS libelle,
				   MAX(ec.ref_doc) AS ref_doc,
				   ROUND(SUM(ec.debit), 3) AS total_debit,
				   ROUND(SUM(ec.credit), 3) AS total_credit,
				   '{ENTRY_DOCTYPE_LABELS[LEDGER_DOCTYPE]}' AS entry_type,
				   MAX(CASE WHEN ec.import_batch IS NOT NULL AND ec.import_batch != '' THEN 1 ELSE 0 END) AS imported,
				   MAX(CASE WHEN ec.lettrage_status != 'Non lettre' OR ec.pointe = 1 THEN 1 ELSE 0 END) AS has_lettered
			FROM `tab{LEDGER_DOCTYPE}` ec
			WHERE {p_l_where}
			GROUP BY COALESCE(ec.journal, ''), COALESCE(ec.mvt, '')
			{p_l_having}
		""")
		all_params.update(p_l_params)

	if not union_parts:
		return {"rows": [], "total": 0, "page": page, "page_size": page_size}

	union_sql = " UNION ALL ".join(union_parts)
	full_sql = f"""
		SELECT * FROM ({union_sql}) combined
		ORDER BY date_operation DESC, journal ASC, mvt ASC
		LIMIT %(limit)s OFFSET %(offset)s
	"""
	all_params["limit"] = page_size
	all_params["offset"] = offset

	rows = frappe.db.sql(full_sql, all_params, as_dict=True)

	return {
		"rows": rows,
		"total": total,
		"page": page,
		"page_size": page_size,
	}


# ── delete ───────────────────────────────────────────────────────────────────


def _reset_facturation_source(doctype: str, name: str) -> None:
	"""Reset the Facturation source document exactly as
	EntryDocument.on_trash does."""
	source = frappe.db.get_value(doctype, name, ["source_doctype", "source_name"], as_dict=True)
	if not source or not source.source_doctype or not source.source_name:
		return
	try:
		frappe.db.set_value(
			source.source_doctype,
			source.source_name,
			{"entry": None, "entry_doctype": None, "entry_status": "Non saisie"},
			update_modified=False,
		)
	except Exception:
		pass  # source may already be deleted


def _clear_lettrage_for_rows(where_clause: str, params: dict[str, Any]) -> None:
	"""Clear lettrage groups and pointage on ledger rows matching where_clause."""
	lettered_rows = frappe.db.sql(
		f"""SELECT name, lettrage_group FROM `tab{LEDGER_DOCTYPE}`
			WHERE {where_clause} AND lettrage_status != 'Non lettre'""",
		params,
		as_dict=True,
	)
	groups_to_clear = {row.lettrage_group for row in lettered_rows if row.lettrage_group}

	for group_name in groups_to_clear:
		frappe.db.sql(
			f"""UPDATE `tab{LEDGER_DOCTYPE}`
				SET lettrage_status = 'Non lettre', lettrage_group = NULL
				WHERE lettrage_group = %(g)s""",
			{"g": group_name},
		)
		if frappe.db.exists("Lettrage Groupe", group_name):
			frappe.delete_doc("Lettrage Groupe", group_name, force=True, ignore_permissions=True)

	frappe.db.sql(
		f"""UPDATE `tab{LEDGER_DOCTYPE}`
			SET pointe = 0
			WHERE {where_clause} AND pointe = 1""",
		params,
	)


def _delete_single_target(
	target: dict[str, str],
	context: dict[str, Any],
	force: bool = False,
) -> str | None:
	"""Delete one entry (or legacy ledger group) + its children + its ledger rows.

	Returns None on success, or a skip-reason string ('lettered').
	"""
	doctype = target["doctype"]
	name = target["name"]

	if doctype == LEDGER_DOCTYPE:
		# Legacy ledger rows with no source_entry, grouped by (entreprise, exercice, journal, mvt)
		journal = target.get("journal")
		mvt = target.get("mvt")
		if journal is None or mvt is None:
			parts = name.split("::", 1)
			journal = parts[0]
			mvt = parts[1] if len(parts) > 1 else ""

		where_clause = (
			"entreprise = %(entreprise)s AND exercice = %(exercice)s "
			"AND COALESCE(journal, '') = %(journal)s AND COALESCE(mvt, '') = %(mvt)s "
			"AND (source_entry IS NULL OR source_entry = '')"
		)
		params = {
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"journal": journal,
			"mvt": mvt,
		}
		locked_names = frappe.db.sql(
			f"""SELECT name FROM `tab{LEDGER_DOCTYPE}` WHERE {where_clause}""",
			params,
			as_dict=True,
		)
		if locked_row_names([row.name for row in locked_names]):
			return "declaration"

		has_lettered = frappe.db.sql(
			f"""SELECT 1 FROM `tab{LEDGER_DOCTYPE}`
				WHERE {where_clause} AND (lettrage_status != 'Non lettre' OR pointe = 1)
				LIMIT 1""",
			params,
		)
		if has_lettered:
			if not force:
				return "lettered"
			_clear_lettrage_for_rows(where_clause, params)

		frappe.db.sql(f"DELETE FROM `tab{LEDGER_DOCTYPE}` WHERE {where_clause}", params)
		return None

	where_clause = "source_entry_doctype = %(dt)s AND source_entry = %(name)s"
	params = {"dt": doctype, "name": name}

	row_names = frappe.get_all(LEDGER_DOCTYPE, filters={"source_entry_doctype": doctype, "source_entry": name}, pluck="name")
	locked = locked_row_names(row_names)
	if locked:
		return "declaration"

	has_lettered = frappe.db.sql(
		f"""SELECT 1 FROM `tab{LEDGER_DOCTYPE}`
			WHERE {where_clause} AND (lettrage_status != 'Non lettre' OR pointe = 1)
			LIMIT 1""",
		params,
	)

	if has_lettered:
		if not force:
			return "lettered"
		_clear_lettrage_for_rows(where_clause, params)

	# 1. reset facturation source
	_reset_facturation_source(doctype, name)

	# 2. delete ledger rows
	frappe.db.delete(LEDGER_DOCTYPE, {"source_entry_doctype": doctype, "source_entry": name})

	# 3. delete child table rows (Ecriture Ligne for the entries, the DM
	# rubriques for a Declaration Transaction)
	child_doctypes = (
		(CHILD_DOCTYPE, "lines"),
		(DECLARATION_LINE_DOCTYPE, "rubriques"),
	) if doctype == "Declaration Transaction" else ((CHILD_DOCTYPE, "lines"),)
	for child_dt, parentfield in child_doctypes:
		frappe.db.sql(
			f"""DELETE FROM `tab{child_dt}` WHERE parenttype = %(dt)s AND parent = %(name)s
				AND (parentfield = %(pf)s OR parentfield IS NULL OR parentfield = '')""",
			{**params, "pf": parentfield},
		)

	# 4. delete entry itself
	frappe.db.sql(f"""DELETE FROM `tab{doctype}` WHERE name = %(name)s""", {"name": name})

	return None


def _log_deletion(
	context: dict[str, Any],
	filters: dict[str, Any],
	deleted: int,
	skipped: int,
	failed: int,
	forced: int,
) -> None:
	"""Log the deletion as a Comment on the Suppression Ecritures single."""
	summary = (
		f"Suppression: {deleted} supprimées, {skipped} ignorées (lettrées/pointées), "
		f"{failed} échouées, {forced} forcées. "
		f"Contexte: {context.get('entreprise')} / {context.get('exercice')}. "
		f"Filtres: {json.dumps(filters, default=str, ensure_ascii=False)}"
	)
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Suppression Ecritures",
			"reference_name": "Suppression Ecritures",
			"content": summary,
			"comment_email": frappe.session.user,
		}
	).insert(ignore_permissions=True)


def _is_pure_imported_delete(filters: dict[str, Any]) -> bool:
	"""True when the only active filter is origin == 'Imported'."""
	if filters.get("origin") != "Imported":
		return False
	other_keys = {"journal", "mvt", "ref_doc", "date_from", "date_to", "compte", "libelle", "entry_type"}
	return not any(filters.get(k) for k in other_keys)


@frappe.whitelist(methods=["POST"])
def delete_transactions(
	names: str | list | None = None,
	filters: str | dict | None = None,
	select_all: int = 0,
	force: int = 0,
) -> dict[str, Any]:
	"""Delete selected transactions (or all matching) with their ledger rows.

	- ``names``: JSON list of ``{"name": "...", "doctype": "..."}`` dicts.
	- ``filters`` + ``select_all=1``: delete everything matching the filters.
	- ``force=1`` (System Manager only): clear lettrage before deleting.

	Returns ``{"deleted": N, "skipped": N, "failed": N, "forced": N}``.
	Large batches (>CHUNK_SIZE) run with chunk-commits and progress.
	"""
	_check_roles()
	context = require_context()
	validate_exercice_open(context)

	force_flag = bool(cint(force))
	if force_flag and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Seul un System Manager peut forcer la suppression d'écritures lettrées."),
			frappe.PermissionError,
		)

	f = _parse_filters(filters)

	# Reuse reports.imported_entries.delete_imported_entries when deleting all
	# imported entries with no extra filters and no flagged rows
	if cint(select_all) and not force_flag and _is_pure_imported_delete(f):
		if not flagged_linked_rows(context):
			deleted_entries = delete_imported_entries(context)
			# Also remove any remaining unlinked imported ledger rows
			frappe.db.sql(
				f"""DELETE FROM `tab{LEDGER_DOCTYPE}`
					WHERE entreprise = %(entreprise)s AND exercice = %(exercice)s
					  AND import_batch IS NOT NULL AND import_batch != ''
					  AND (lettrage_status = 'Non lettre' AND pointe = 0)""",
				{"entreprise": context["entreprise"], "exercice": context["exercice"]},
			)
			frappe.db.commit()
			_log_deletion(context, f, deleted_entries, 0, 0, 0)
			return {"deleted": deleted_entries, "skipped": 0, "failed": 0, "forced": 0}

	# resolve the target list
	targets: list[dict[str, str]] = []
	if cint(select_all):
		doctypes = _entry_type_doctypes(f.get("entry_type"))
		for dt in doctypes:
			where_sql, params = _build_entry_where(dt, f, context)
			rows = frappe.db.sql(
				f"SELECT name FROM `tab{dt}` e WHERE {where_sql}",
				params,
				as_dict=True,
			)
			for row in rows:
				targets.append({"name": row.name, "doctype": dt})

		if _include_legacy(f.get("entry_type")):
			l_where, l_having, l_params = _build_legacy_where(f, context)
			legacy_rows = frappe.db.sql(
				f"""SELECT COALESCE(ec.journal, '') AS journal, COALESCE(ec.mvt, '') AS mvt
					FROM `tab{LEDGER_DOCTYPE}` ec
					WHERE {l_where}
					GROUP BY COALESCE(ec.journal, ''), COALESCE(ec.mvt, '')
					{l_having}""",
				l_params,
				as_dict=True,
			)
			for row in legacy_rows:
				targets.append({
					"name": f"{row.journal}::{row.mvt}",
					"doctype": LEDGER_DOCTYPE,
					"journal": row.journal,
					"mvt": row.mvt,
				})
	else:
		raw_names = names
		if isinstance(raw_names, str):
			raw_names = json.loads(raw_names)
		if raw_names:
			for n in raw_names:
				item = {"name": n["name"], "doctype": n["doctype"]}
				if "journal" in n:
					item["journal"] = n["journal"]
				if "mvt" in n:
					item["mvt"] = n["mvt"]
				targets.append(item)

	if not targets:
		return {"deleted": 0, "skipped": 0, "failed": 0, "forced": 0}

	# if large batch, run as background job
	if len(targets) > CHUNK_SIZE:
		job_id = f"suppression_ecritures_{context['entreprise']}_{context['exercice']}"
		try:
			frappe.enqueue(
				_delete_batch_job,
				queue="long",
				timeout=3600,
				job_id=job_id,
				deduplicate=True,
				targets=targets,
				context=context,
				force=force_flag,
				filters=f,
			)
		except Exception:
			frappe.log_error("Suppression ecritures enqueue failed", frappe.get_traceback())
			frappe.throw(_("Impossible de lancer la suppression en arrière-plan."))
		return {"enqueued": 1, "job_id": job_id, "count": len(targets)}

	# synchronous for small batches
	result = _delete_targets(targets, context, force_flag)
	_log_deletion(context, f, result["deleted"], result["skipped"], result["failed"], result["forced"])
	return result


def _delete_batch_job(
	targets: list[dict[str, str]],
	context: dict[str, Any],
	force: bool,
	filters: dict[str, Any],
) -> None:
	"""Background job: delete in chunks with progress."""
	total = len(targets)
	deleted = 0
	skipped = 0
	failed = 0
	forced = 0

	for i, target in enumerate(targets):
		try:
			reason = _delete_single_target(target, context, force=force)
			if reason is None:
				deleted += 1
				if force:
					forced += 1
			elif reason == "lettered":
				skipped += 1
			elif reason == "declaration":
				skipped += 1
			else:
				failed += 1
		except Exception:
			frappe.log_error(
				f"Suppression failed: {target['doctype']} {target['name']}",
				frappe.get_traceback(),
			)
			failed += 1

		if (i + 1) % CHUNK_SIZE == 0:
			frappe.db.commit()
			frappe.publish_progress(
				percent=((i + 1) / total) * 100,
				title=_("Suppression des écritures"),
				description=_(
					"{0}/{1} traitées — {2} supprimées, {3} ignorées"
				).format(i + 1, total, deleted, skipped),
			)

	frappe.db.commit()
	_log_deletion(context, filters, deleted, skipped, failed, forced)
	frappe.publish_progress(
		percent=100,
		title=_("Suppression des écritures"),
		description=_(
			"Terminé: {0} supprimées, {1} ignorées, {2} échouées"
		).format(deleted, skipped, failed),
	)


def _delete_targets(
	targets: list[dict[str, str]],
	context: dict[str, Any],
	force: bool,
) -> dict[str, int]:
	"""Synchronous delete loop."""
	deleted = 0
	skipped = 0
	failed = 0
	forced_count = 0

	for target in targets:
		try:
			reason = _delete_single_target(target, context, force=force)
			if reason is None:
				deleted += 1
				if force:
					forced_count += 1
			elif reason == "lettered":
				skipped += 1
			elif reason == "declaration":
				skipped += 1
			else:
				failed += 1
		except Exception:
			frappe.log_error(
				f"Suppression failed: {target['doctype']} {target['name']}",
				frappe.get_traceback(),
			)
			failed += 1

	return {"deleted": deleted, "skipped": skipped, "failed": failed, "forced": forced_count}


@frappe.whitelist()
def count_transactions(
	filters: str | dict | None = None,
) -> dict[str, Any]:
	"""Count matching transactions per entry type (plus legacy) and lettered count."""
	_check_roles()
	context = require_context()
	f = _parse_filters(filters)
	doctypes = _entry_type_doctypes(f.get("entry_type"))

	counts: dict[str, int] = {}
	total = 0
	lettered = 0

	for dt in doctypes:
		where_sql, params = _build_entry_where(dt, f, context)
		c = cint(frappe.db.sql(f"SELECT COUNT(*) FROM `tab{dt}` e WHERE {where_sql}", params)[0][0])
		counts[ENTRY_DOCTYPE_LABELS.get(dt, dt)] = c
		total += c

		let_c = cint(frappe.db.sql(
			f"""SELECT COUNT(DISTINCT e.name) FROM `tab{dt}` e
				INNER JOIN `tab{LEDGER_DOCTYPE}` ec
				  ON ec.source_entry_doctype = '{dt}' AND ec.source_entry = e.name
				WHERE {where_sql}
				  AND (ec.lettrage_status != 'Non lettre' OR ec.pointe = 1)""",
			params,
		)[0][0])
		lettered += let_c

	if _include_legacy(f.get("entry_type")):
		l_where, l_having, l_params = _build_legacy_where(f, context)
		leg_rows = frappe.db.sql(
			f"""SELECT MAX(CASE WHEN ec.lettrage_status != 'Non lettre' OR ec.pointe = 1 THEN 1 ELSE 0 END) AS has_let
				FROM `tab{LEDGER_DOCTYPE}` ec
				WHERE {l_where}
				GROUP BY COALESCE(ec.journal, ''), COALESCE(ec.mvt, '')
				{l_having}""",
			l_params,
			as_dict=True,
		)
		leg_c = len(leg_rows)
		counts[ENTRY_DOCTYPE_LABELS[LEDGER_DOCTYPE]] = leg_c
		total += leg_c
		lettered += sum(1 for r in leg_rows if r.has_let)

	return {"counts": counts, "total": total, "lettered": lettered}
