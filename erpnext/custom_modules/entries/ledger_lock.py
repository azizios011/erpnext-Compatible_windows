# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""One guard for EVERY write path into the Ecriture Comptable ledger: a row
stamped declaration_cloture belongs to a clotured Déclaration Mensuelle and
must neither be edited nor deleted. The workflow unlocks it through
decloture_declaration, nothing else.

Callers: EntryDocument.post_to_ledger / on_trash (the delete-and-repost
rewrite), the grand-livre import (replace + delete), the Suppression des
Ecritures screen (which SKIPS locked rows instead of throwing), the lettrage
writes and the imported-entries materialization link. The Ecriture Comptable
doc controller re-checks direct desk edits.
"""

import frappe
from frappe import _

LEDGER_DOCTYPE = "Ecriture Comptable"


def _declaration_of(row_name: str) -> str:
	return frappe.db.get_value(LEDGER_DOCTYPE, row_name, "declaration_cloture") or ""


def assert_row_not_declaration_locked(row_name: str, action: str = "modifier") -> None:
	"""Refuse to touch one ledger row stamped by a clotured declaration."""
	if not row_name:
		return
	declaration = _declaration_of(row_name)
	if declaration:
		frappe.throw(
			_("L'ecriture {0} est verrouillee par la declaration {1} (cloturee): {2} impossible.").format(
				frappe.bold(row_name), frappe.bold(declaration), _(action)
			)
		)


def assert_rows_not_declaration_locked(row_names: list[str], action: str = "modifier") -> None:
	"""Refuse to touch any of the named ledger rows; names the declaration."""
	names = [name for name in (row_names or []) if name]
	if not names:
		return
	locked = frappe.get_all(
		LEDGER_DOCTYPE,
		filters={"name": ("in", names), "declaration_cloture": ("is", "set")},
		fields=["name", "declaration_cloture"],
		limit=1,
	)
	if locked:
		frappe.throw(
			_("L'ecriture {0} est verrouillee par la declaration {1} (cloturee): {2} impossible.").format(
				frappe.bold(locked[0].name), frappe.bold(locked[0].declaration_cloture), _(action)
			)
		)


def assert_entry_ledger_not_locked(source_entry_doctype: str, source_entry: str, action: str = "modifier") -> None:
	"""Re-posting or deleting an entry rewrites its ledger rows: refuse when
	any of them is stamped by a clotured declaration."""
	if not (source_entry_doctype and source_entry):
		return
	locked = frappe.get_all(
		LEDGER_DOCTYPE,
		filters={
			"source_entry_doctype": source_entry_doctype,
			"source_entry": source_entry,
			"declaration_cloture": ("is", "set"),
		},
		fields=["name", "declaration_cloture"],
		limit=1,
	)
	if locked:
		frappe.throw(
			_("Les ecritures de {0} {1} sont verrouillees par la declaration {2} (cloturee): {3} impossible.").format(
				_(source_entry_doctype),
				frappe.bold(source_entry),
				frappe.bold(locked[0].declaration_cloture),
				_(action),
			)
		)


def locked_row_names(row_names: list[str]) -> list[dict]:
	"""Non-throwing variant for bulk flows that SKIP locked rows (the
	Suppression des Ecritures screen reports them per row)."""
	names = [name for name in (row_names or []) if name]
	if not names:
		return []
	return frappe.get_all(
		LEDGER_DOCTYPE,
		filters={"name": ("in", names), "declaration_cloture": ("is", "set")},
		fields=["name", "declaration_cloture"],
	)


def any_row_locked_by_filter(filters: dict) -> bool:
	"""Whether ANY ledger row matching the filters carries the stamp."""
	if not filters:
		return False
	return bool(
		frappe.get_all(
			LEDGER_DOCTYPE,
			filters={**filters, "declaration_cloture": ("is", "set")},
			limit=1,
		)
	)
