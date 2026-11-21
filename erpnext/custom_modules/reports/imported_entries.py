# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Materialize imported Grand Livre movements into real Entries.

Today the rows imported from a Grand Livre xlsx (ledger_import.py) carry no
source entry, so the Ledger Data eye icon cannot open anything. This module
turns EVERY imported movement into one transaction in the Entries workspace:

- one entry per group of imported ledger rows sharing the same
  (entreprise, exercice, journal, mvt) — the imported MVT number and posting
  date are KEPT (no new MVT allocation);
- classification: supplier-auxiliary lines (AUX_FOURNISSEUR_PREFIX, 401...)
  → Payable Transaction, client-auxiliary lines (AUX_CLIENT_PREFIX, 411...)
  → Receivable Transaction. The sign (invoice vs payment) only changes the
  line direction, never the doctype. When a group carries BOTH kinds, the
  journal's journal_type is the tie-breaker (purchase journals → Payable,
  sales journals → Receivable); a mixed group under a neutral journal
  (Banque, Declaration, Operations Diverses) stays unclassified and is
  reported. Groups with neither kind (opening balances AN, capital, pure
  bank/tax lines) are left unlinked on purpose;
- the entries are created AS ALREADY POSTED (status "Comptabilise"), flagged
  imported + import_batch, written with frappe.db.bulk_insert so NO controller
  hook fires and no new ledger rows are posted; the EXISTING imported ledger
  rows get source_entry_doctype / source_entry set instead;
- idempotent: rows that already carry a source entry are skipped, and an
  imported entry left over by an interrupted run is rebuilt in place.

Re-saving an imported entry goes through the normal EntryDocument.on_update
path: post_to_ledger deletes that source entry's ledger rows and recreates
them from the lines — safe and idempotent EXCEPT that the recreated rows
lose lettrage/pointe/import_batch; and validate_ledger_not_lettered blocks
the save with a clear message when any linked row is already lettree or
pointee (entry_base.py).

Every entry point requires the Accounts Manager / System Manager role and
the strict accounting context; writes require an Ouvert Exercice.
"""

import frappe
from frappe import _
from frappe.utils import cint, getdate

from erpnext.custom_modules.organization.context import require_context, validate_exercice_open
from erpnext.custom_modules.reports.imported_entries_logic import (
	PAYABLE_DOCTYPE,
	RECEIVABLE_DOCTYPE,
	build_entry_payload,
	materialize_plan,
)
from erpnext.custom_modules.reports import check_import_roles

LEDGER_DOCTYPE = "Ecriture Comptable"
CHILD_DOCTYPE = "Ecriture Ligne"

# the background run commits and reports progress every N groups
CHUNK_SIZE = 500


# ── Frappe I/O ───────────────────────────────────────────────────────────────


def _imported_rows(context: dict) -> list:
	"""The imported ledger rows of this context that still carry no source
	entry — the materialization input. Idempotency: already-linked rows are
	skipped, re-running never duplicates."""
	return frappe.get_all(
		LEDGER_DOCTYPE,
		filters={
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"import_batch": ("is", "set"),
			"source_entry": ("is", "not set"),
		},
		fields=[
			"name",
			"posting_date",
			"journal",
			"mvt",
			"account",
			"libelle",
			"debit",
			"credit",
			"ref_doc",
			"tresorerie",
			"import_batch",
			"entreprise",
			"exercice",
		],
		order_by="creation asc",
	)


def _reference_data(row_accounts: set[str], journals: set[str]) -> tuple[dict[str, str], dict[str, str]]:
	"""(account name → account_number, journal code → journal_type), each in
	ONE query."""
	account_numbers = {
		row.name: row.account_number
		for row in frappe.get_all(
			"Chart of Account",
			filters={"name": ("in", sorted(row_accounts))},
			fields=["name", "account_number"],
		)
	}
	journal_types = {
		row.name: row.journal_type
		for row in frappe.get_all(
			"Journal",
			filters={"name": ("in", sorted(journals))},
			fields=["name", "journal_type"],
		)
	}
	return account_numbers, journal_types


def _existing_entry_names(entry_doctypes: tuple[str, ...], mvts: list[str]) -> dict[str, dict[str, int]]:
	"""(doctype → mvt → imported flag) for the entry names that already
	exist. An existing IMPORTED entry is rebuilt in place (interrupted-run
	leftover); a foreign one is a real name conflict, the group is skipped."""
	out: dict[str, dict[str, int]] = {}
	for doctype in entry_doctypes:
		out[doctype] = {
			row.name: cint(row.imported)
			for row in frappe.get_all(
				doctype,
				filters={"name": ("in", mvts)},
				fields=["name", "imported"],
			)
		}
	return out


def _insert_entry(doctype: str, parent: dict, lines: list[dict]) -> None:
	"""Bulk-insert one entry (parent + its lines) WITHOUT running any
	controller hook — nothing re-posts to the ledger behind our back."""
	now = frappe.utils.now_datetime()
	user = frappe.session.user
	parent_fields = [
		"name",
		"creation",
		"modified",
		"modified_by",
		"owner",
		"docstatus",
		"idx",
		"date_operation",
		"journal",
		"mois",
		"jour",
		"devise",
		"mvt",
		"ref_doc",
		"libelle",
		"source_doctype",
		"source_name",
		"entreprise",
		"exercice",
		"total_debit",
		"total_credit",
		"solde",
		"status",
		"imported",
		"import_batch",
	]
	parent_values = (
		parent["name"],
		now,
		now,
		user,
		user,
		0,
		0,
		parent["date_operation"],
		parent["journal"],
		parent["mois"],
		parent["jour"],
		parent["devise"],
		parent["mvt"],
		parent["ref_doc"],
		parent["libelle"],
		parent["source_doctype"],
		parent["source_name"],
		parent["entreprise"],
		parent["exercice"],
		parent["total_debit"],
		parent["total_credit"],
		parent["solde"],
		parent["status"],
		parent["imported"],
		parent["import_batch"],
	)
	frappe.db.bulk_insert(doctype, fields=parent_fields, values=[parent_values], chunk_size=1)

	child_fields = [
		"name",
		"creation",
		"modified",
		"modified_by",
		"owner",
		"docstatus",
		"idx",
		"parent",
		"parenttype",
		"parentfield",
		"account",
		"libelle",
		"fact",
		"tresorerie",
		"debit",
		"credit",
	]
	child_values = [
		(
			frappe.generate_hash(length=10),
			now,
			now,
			user,
			user,
			0,
			line["idx"],
			parent["name"],
			doctype,
			"lines",
			line["account"],
			line["libelle"],
			line["fact"],
			line["tresorerie"],
			line["debit"],
			line["credit"],
		)
		for line in lines
	]
	frappe.db.bulk_insert(CHILD_DOCTYPE, fields=child_fields, values=child_values, chunk_size=1)


def _delete_entry(doctype: str, name: str) -> None:
	"""Delete one imported entry (lines first) — only ever called on entries
	flagged imported (interrupted-run leftovers)."""
	frappe.db.delete(CHILD_DOCTYPE, {"parenttype": doctype, "parent": name, "parentfield": "lines"})
	frappe.db.delete(doctype, {"name": name})


def _link_rows(doctype: str, name: str, row_names: list[str]) -> None:
	"""Point the EXISTING imported ledger rows at the entry (no new rows)."""
	frappe.db.sql(
		f"""update `tab{LEDGER_DOCTYPE}`
			set source_entry_doctype = %(doctype)s, source_entry = %(name)s
			where name in %(names)s""",
		{"doctype": doctype, "name": name, "names": tuple(row_names)},
	)


def _run_materialization(context: dict, dry_run: int) -> dict:
	rows = _imported_rows(context)
	account_numbers, journal_types = _reference_data(
		{row.account for row in rows}, {row.journal for row in rows}
	)
	built = materialize_plan(rows, journal_types, account_numbers)
	plan = built["plan"]
	per_journal = built["per_journal"]

	mvts = [mvt for _, mvt, _ in plan[PAYABLE_DOCTYPE] + plan[RECEIVABLE_DOCTYPE]]
	existing = _existing_entry_names((PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE), mvts) if mvts else {}

	result = {
		"dry_run": cint(dry_run),
		"rows_total": len(rows),
		"rows_already_linked": frappe.db.count(
			LEDGER_DOCTYPE,
			{
				"entreprise": context["entreprise"],
				"exercice": context["exercice"],
				"import_batch": ("is", "set"),
				"source_entry": ("is", "set"),
			},
		),
		"groups_total": sum(len(v) for v in plan.values()),
		"created": {PAYABLE_DOCTYPE: 0, RECEIVABLE_DOCTYPE: 0},
		"rebuilt": 0,
		"skipped_name_conflict": 0,
		"rows_linked": 0,
		"unclassified_groups": len(plan[None]),
		"unclassified_rows": sum(len(group) for _, _, group in plan[None]),
		"per_journal": per_journal,
	}
	if dry_run:
		for doctype in (PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE):
			conflicts = sum(1 for _, mvt, _ in plan[doctype] if existing.get(doctype, {}).get(mvt) == 0)
			result["skipped_name_conflict"] += conflicts
			result["created"][doctype] = len(plan[doctype]) - conflicts
		result["rows_linked"] = sum(
			len(group)
			for doctype in (PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE)
			for _, mvt, group in plan[doctype]
			if existing.get(doctype, {}).get(mvt) != 0
		)
		return result

	validate_exercice_open(context)
	processed = 0
	total_groups = result["groups_total"] or 1
	for doctype in (PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE):
		for journal, mvt, group_rows in plan[doctype]:
			leftover_imported = existing.get(doctype, {}).get(mvt)
			if leftover_imported == 0:
				# a foreign document already owns this MVT: never touch it
				result["skipped_name_conflict"] += 1
				processed += 1
				continue
			if leftover_imported == 1:
				# leftover of an interrupted run: rebuild it in place
				_delete_entry(doctype, mvt)
				result["rebuilt"] += 1
			batches = ", ".join(sorted({row.import_batch for row in group_rows if row.import_batch}))
			posting_date = min(getdate(row.posting_date) for row in group_rows)
			parent, lines = build_entry_payload(doctype, journal, mvt, posting_date, batches, group_rows)
			_insert_entry(doctype, parent, lines)
			_link_rows(doctype, mvt, [row.name for row in group_rows])
			result["created"][doctype] += 1
			result["rows_linked"] += len(group_rows)
			processed += 1
			_bump_progress(context, processed, total_groups)
			if processed % CHUNK_SIZE == 0:
				frappe.db.commit()  # chunked commits keep the job resumable
	frappe.db.commit()  # the final chunk
	return result


def _bump_progress(context: dict, processed: int, total_groups: int) -> None:
	if processed % 100 == 0:
		message = _("Ecritures de l'import: {0}/{1} mouvements traites.").format(processed, total_groups)
		frappe.publish_realtime(
			"grand_livre_materialize_progress",
			{
				"entreprise": context["entreprise"],
				"exercice": context["exercice"],
				"processed": processed,
				"total": total_groups,
				"progress": message,
			},
			user=frappe.session.user,
		)


@frappe.whitelist()
def materialize_imported_entries(dry_run: int = 1) -> dict:
	"""Counts per doctype / per journal / unclassified for the imported
	movements of the current Entreprise + Exercice. dry_run=1 (the default)
	writes nothing; dry_run=0 runs the real materialization synchronously —
	the UI path goes through enqueue_materialize_imported_entries instead."""
	check_import_roles()
	context = require_context()
	return _run_materialization(context, dry_run)


@frappe.whitelist(methods=["POST"])
def enqueue_materialize_imported_entries() -> dict:
	"""The UI path: enqueue the real run as a long background job (it creates
	several thousand entries). Idempotent per Entreprise + Exercice via the
	job id."""
	check_import_roles()
	context = require_context()
	job_id = f"gl_materialize_{context['entreprise']}_{context['exercice']}"
	try:
		frappe.enqueue(
			"erpnext.custom_modules.reports.imported_entries.materialize_imported_entries_job",
			queue="long",
			timeout=3600,
			job_id=job_id,
			deduplicate=True,
		)
	except Exception:
		frappe.log_error("Grand Livre materialize enqueue failed", frappe.get_traceback())
		return {"enqueued": 0, "error": _("La file de taches de fond est indisponible: reessayez plus tard.")}
	return {"enqueued": 1, "job_id": job_id}


def materialize_imported_entries_job() -> None:
	"""The enqueued real run (long queue, chunked commits, progress through
	publish_realtime)."""
	context = require_context()
	result = _run_materialization(context, dry_run=0)
	frappe.publish_realtime(
		"grand_livre_materialize_progress",
		{
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"processed": result["groups_total"],
			"total": result["groups_total"],
			"progress": _("Termine: {0}.").format(
				" + ".join(f"{count} {doctype}" for doctype, count in result["created"].items())
			),
		},
		user=frappe.session.user,
	)


def delete_imported_entries(context: dict) -> int:
	"""Delete the imported entries of this Entreprise + Exercice (ONLY those
	flagged imported) and every ledger row still pointing at them (the
	import-batch rows plus the rows a re-save of an imported entry
	re-posted), so 'Supprimer l'import' leaves nothing behind. Returns the
	number of deleted entries."""
	deleted = 0
	for doctype in (PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE):
		names = frappe.get_all(
			doctype,
			filters={
				"entreprise": context["entreprise"],
				"exercice": context["exercice"],
				"imported": 1,
			},
			pluck="name",
		)
		if not names:
			continue
		frappe.db.sql(
			f"""delete from `tab{LEDGER_DOCTYPE}`
                where source_entry_doctype = %(doctype)s and source_entry in %(names)s""",
			{"doctype": doctype, "names": tuple(names)},
		)
		for name in names:
			_delete_entry(doctype, name)
			deleted += 1
	return deleted


def flagged_linked_rows(context: dict) -> list[str]:
	"""Ledger rows linked to an imported entry (whatever their batch) that
	are lettree or pointee — 'Supprimer l'import' / replace must refuse while
	any of them exists (the lettrage would be destroyed)."""
	entry_names: list[str] = []
	for doctype in (PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE):
		entry_names.extend(
			frappe.get_all(
				doctype,
				filters={
					"entreprise": context["entreprise"],
					"exercice": context["exercice"],
					"imported": 1,
				},
				pluck="name",
			)
		)
	if not entry_names:
		return []
	return frappe.get_all(
		LEDGER_DOCTYPE,
		filters={
			"source_entry_doctype": ("in", (PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE)),
			"source_entry": ("in", entry_names),
		},
		or_filters=[
			[LEDGER_DOCTYPE, "lettrage_status", "!=", "Non lettre"],
			[LEDGER_DOCTYPE, "pointe", "=", 1],
		],
		pluck="name",
	)
