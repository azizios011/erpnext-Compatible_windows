import os

import frappe


def get_custom_module_names() -> list[str]:
	base_dir = os.path.dirname(os.path.abspath(__file__))
	modules = []
	for name in sorted(os.listdir(base_dir)):
		if name in ("__pycache__", "__init__.py", "setup.py") or name.startswith("."):
			continue
		full_path = os.path.join(base_dir, name)
		if os.path.isdir(full_path):
			label = name.replace("_", " ").title()
			modules.append(label)
	return modules


def fix_workspace_hierarchy():
	for module_label in get_custom_module_names():
		if not frappe.db.exists("Workspace", {"module": module_label, "name": module_label}):
			continue

		workspaces = frappe.get_all(
			"Workspace",
			filters={"module": module_label},
			fields=["name", "parent_page"],
		)

		for ws in workspaces:
			if ws.name == module_label:
				continue

			if ws.parent_page != module_label:
				doc = frappe.get_doc("Workspace", ws.name)
				doc.parent_page = module_label
				doc.save(ignore_permissions=True)


def dedupe_home_links():
	if not frappe.db.exists("Workspace", "Home"):
		return

	doc = frappe.get_doc("Workspace", "Home")
	seen = set()
	new_links = []
	has_duplicates = False

	for item in doc.links:
		key = (item.get("type"), item.get("label"), item.get("link_to"))
		if key in seen:
			has_duplicates = True
		else:
			seen.add(key)
			new_links.append(item)

	if has_duplicates:
		doc.links = new_links
		doc.save(ignore_permissions=True)


def clear_module_map_cache():
	"""`frappe.local.app_modules` (the list of modules a migrate will sync) is loaded from a
	Redis-cached `app_modules` key at `frappe.init()` time -- *before* migrate's own
	`frappe.clear_cache()` runs. That means a migrate which adds a brand-new
	custom_modules/<folder> can silently run against a stale cached module list and skip
	syncing that folder's doctypes/workspaces/pages entirely, with no error surfaced.
	Clearing the cache key here (at the end of install/migrate) guarantees the *next*
	migrate run starts with a fresh disk scan, so a newly added custom module is picked up
	after one extra `bench migrate` instead of requiring a full site reinstall."""
	frappe.cache.delete_value("app_modules")
	frappe.cache.delete_value("installed_app_modules")


def force_reload_custom_workspaces():
	"""Force-reload each custom module's own workspace fixture from disk on every
	install/migrate, bypassing the modified-timestamp check that can otherwise cause
	normal fixture sync to permanently skip re-syncing a workspace once its DB record
	has been resaved outside of a plain import."""
	for module_label in get_custom_module_names():
		module_name = frappe.scrub(module_label)
		if not frappe.db.exists("Workspace", module_label):
			continue
		try:
			frappe.reload_doc(module_name, "workspace", module_name, force=True)
		except OSError:
			# No workspace fixture file for this module — nothing to reload.
			continue
	frappe.db.commit()



def rename_sales_taxes_template():
	"""Sites installed before the Tax Template rename still carry the old DocType.
	This migrate's sync has already created the renamed doctype from its JSON, so
	merge the old one into it: rows move across and every stored Link reference
	is pointed at the new name in one step, matching erpnext's own rename patches."""
	old, new = "Sales Taxes and Charges Template", "Tax Template"
	if not frappe.db.exists("DocType", old):
		return
	if not frappe.db.exists("DocType", new):
		frappe.rename_doc("DocType", old, new, force=True)
	else:
		frappe.rename_doc("DocType", old, new, merge=True, force=True)
	frappe.reload_doctype(new, force=True)


def after_install():
	force_reload_custom_workspaces()
	fix_workspace_hierarchy()
	dedupe_home_links()
	clear_module_map_cache()
	rename_sales_taxes_template()


def after_migrate():
	force_reload_custom_workspaces()
	fix_workspace_hierarchy()
	dedupe_home_links()
	clear_module_map_cache()
	rename_sales_taxes_template()
