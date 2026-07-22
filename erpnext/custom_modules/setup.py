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


def after_install():
	fix_workspace_hierarchy()
	dedupe_home_links()


def after_migrate():
	fix_workspace_hierarchy()
	dedupe_home_links()
