# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Axeane search scope.

For everyone except Administrator the awesome bar and the global search
only SHOW items belonging to the custom modules (or linked from their
sidebars). This is a display filter, not a permission change: direct URLs
and the sidebar keep working — every underlying query stays
permission-checked by frappe itself.
"""

from typing import Any

import frappe
from frappe import _

# kinds the search modal knows about
KINDS = ("doctypes", "reports", "pages", "workspaces", "dashboards")


def custom_module_names() -> set[str]:
	"""The Axeane custom module labels, derived from the
	custom_modules/<folder> layout (mirrors frappe.modules.utils's own
	discovery)."""
	from erpnext.custom_modules.setup import get_custom_module_names

	return set(get_custom_module_names())


def sidebar_linked_entities(modules: set[str]) -> dict[str, set[str]]:
	"""Entities reachable from the custom modules' Workspace Sidebars, so
	core doctypes and reports those sidebars link to (Bank, Bank Account,
	Fiscal Year, the bank reports, …) stay searchable."""
	out = {kind: set() for kind in KINDS}
	sidebars = frappe.get_all("Sidebar", filters={"name": ("in", modules)}, pluck="name")
	if not sidebars:
		return out
	items = frappe.get_all(
		"Sidebar Item",
		filters={"parent": ("in", sidebars), "parenttype": "Sidebar"},
		fields=["type", "link_type", "link_to"],
	)
	kind_by_link_type = {"DocType": "doctypes", "Report": "reports", "Page": "pages", "Workspace": "workspaces"}
	for item in items:
		if item.type != "Link" or not item.link_to:
			continue
		kind = kind_by_link_type.get(item.link_type)
		if kind:
			out[kind].add(item.link_to)
	return out


def _module_entities(modules: set[str]) -> dict[str, set[str]]:
	out = {kind: set() for kind in KINDS}
	out["doctypes"] = set(
		frappe.get_all("DocType", filters={"module": ("in", modules)}, pluck="name")
	)
	out["reports"] = set(
		frappe.get_all("Report", filters={"module": ("in", modules)}, pluck="name")
	)
	out["pages"] = set(frappe.get_all("Page", filters={"module": ("in", modules)}, pluck="name"))
	out["workspaces"] = set(
		frappe.get_all("Workspace", filters={"module": ("in", modules)}, pluck="name")
	)
	return out


def get_scope() -> dict[str, list[str]] | None:
	"""The search allowlist for the current user; None = unrestricted
	(Administrator, or an error computing the scope must not blind the
	user entirely)."""
	if frappe.session.user == "Administrator":
		return None
	try:
		modules = custom_module_names()
		scope = _module_entities(modules)
		linked = sidebar_linked_entities(modules)
		for kind in KINDS:
			scope[kind] |= linked[kind]
		return {kind: sorted(names) for kind, names in scope.items()}
	except Exception:
		frappe.log_error("axeane search scope failed", frappe.get_traceback())
		return None


def boot_scope(bootinfo: frappe._dict) -> None:
	"""extend_bootinfo entry — ships the scope for the client filters."""
	scope = get_scope()
	if scope is not None:
		bootinfo.axeane_search_scope = scope


@frappe.whitelist()
def global_search_search(text: str = "", start: int = 0, limit: int = 20, doctype: str = "") -> list:
	"""override_whitelisted_methods target for frappe.utils.global_search.search.

	Thin wrapper: calls the original (its own permission checks stay in
	charge) and drops the rows whose doctype is outside the user's scope.
	Display filter only — not a permission change."""
	from frappe.utils import global_search as original_module

	results = original_module.search(text, start=start, limit=limit, doctype=doctype)
	scope = get_scope()
	if scope is None:
		return results
	if isinstance(results, list):
		return [row for row in results if row.get("doctype") in scope["doctypes"]]
	return results
