# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Report module-path resolution for custom modules.

frappe's get_report_module_dotted_path builds the dotted path from
module_app + scrub(module) without consulting the custom_modules layout, so
a Script Report shipped in custom_modules/<module>/report fails to import
(No module named 'erpnext.reports'). The override below patches that
helper — custom-module aware, core doctypes untouched — and is applied
idempotently before every delegated query_report.run call.
"""

import frappe


def _patch_report_module_path() -> None:
	import frappe.core.doctype.report.report as report_module

	if getattr(report_module, "__axeane_report_path_patched", False):
		return

	original = report_module.get_report_module_dotted_path

	def patched(module: str, report_name: str) -> str:
		from frappe.modules.utils import get_custom_module_import_map

		custom_map = get_custom_module_import_map("erpnext")
		scrubbed = frappe.scrub(module)
		if scrubbed in custom_map:
			return (
				f"erpnext.{custom_map[scrubbed]}.report."
				f"{frappe.scrub(report_name)}.{frappe.scrub(report_name)}"
			)
		return original(module, report_name)

	report_module.get_report_module_dotted_path = patched
	report_module.__axeane_report_path_patched = True


@frappe.whitelist()
def run(report_name: str, filters: str | dict | None = None, user: str | None = None, ignore_prepared_report: bool = False, custom_columns: str | list | None = None, is_tree: bool = False, parent_field: str | None = None, are_default_filters: bool = True, js_filters: str | list | None = None) -> dict:
	"""override_whitelisted_methods target for frappe.desk.query_report.run:
	patches the custom-module report path, then delegates unchanged."""
	_patch_report_module_path()
	return frappe.desk.query_report.run(
		report_name=report_name,
		filters=filters,
		user=user,
		ignore_prepared_report=ignore_prepared_report,
		custom_columns=custom_columns,
		is_tree=is_tree,
		parent_field=parent_field,
		are_default_filters=are_default_filters,
		js_filters=js_filters,
	)
