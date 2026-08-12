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


def import_pct_chart_of_accounts():
	json_path = os.path.join(
		os.path.dirname(os.path.abspath(__file__)),
		"general_accounting",
		"doctype",
		"chart_of_accounts",
		"data",
		"pct_chart_of_accounts.json",
	)
	if not os.path.exists(json_path):
		return

	with open(json_path, "r", encoding="utf-8") as f:
		records = frappe.parse_json(f.read())

	for row in records:
		account_val = row.get("account")
		if not account_val:
			continue
		if not frappe.db.exists("Chart of Accounts", account_val):
			doc = frappe.get_doc(
				{
					"doctype": "Chart of Accounts",
					"account": account_val,
					"label": row.get("label", ""),
					"is_group": row.get("is_group", 0),
					"parent_account": row.get("parent_account", ""),
					"account_type": row.get("account_type", ""),
					"nature": row.get("nature", "In Progress"),
					"direction": row.get("direction", ""),
				}
			)
			doc.insert(ignore_permissions=True)


def install_company_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	custom_fields = {
		"Company": [
			{
				"fieldname": "general_info_tab",
				"fieldtype": "Tab Break",
				"label": "General Information",
				"insert_after": "column_break_gthb",
			},
			{
				"fieldname": "status",
				"fieldtype": "Select",
				"label": "Status",
				"options": "\nDraft\nCreated\nTerminated",
				"insert_after": "general_info_tab",
			},
			{
				"fieldname": "activity",
				"fieldtype": "Link",
				"label": "Activity",
				"options": "Business Activity",
				"insert_after": "status",
			},
			{
				"fieldname": "legal_form",
				"fieldtype": "Link",
				"label": "Legal Form",
				"options": "Legal Form",
				"insert_after": "activity",
			},
			{
				"fieldname": "natural_person",
				"fieldtype": "Check",
				"label": "Natural Person",
				"insert_after": "legal_form",
			},
			{
				"fieldname": "general_info_cb1",
				"fieldtype": "Column Break",
				"insert_after": "natural_person",
			},
			{
				"fieldname": "code_exploitation",
				"fieldtype": "Data",
				"label": "Code Exploitation",
				"insert_after": "general_info_cb1",
			},
			{
				"fieldname": "code_exploitation_karama",
				"fieldtype": "Data",
				"label": "Code Exploitation Karama",
				"insert_after": "code_exploitation",
			},
			{
				"fieldname": "convention",
				"fieldtype": "Link",
				"label": "Convention",
				"options": "Convention",
				"insert_after": "code_exploitation_karama",
			},
			{
				"fieldname": "general_info_identifiers_sb",
				"fieldtype": "Section Break",
				"label": "Identifiers",
				"insert_after": "convention",
			},
			{
				"fieldname": "rne_number",
				"fieldtype": "Data",
				"label": "RNE Number",
				"insert_after": "general_info_identifiers_sb",
			},
			{
				"fieldname": "general_info_cb2",
				"fieldtype": "Column Break",
				"insert_after": "rne_number",
			},
			{
				"fieldname": "file_number",
				"fieldtype": "Data",
				"label": "File Number",
				"insert_after": "general_info_cb2",
			},
			{
				"fieldname": "general_info_address_sb",
				"fieldtype": "Section Break",
				"label": "Address",
				"insert_after": "file_number",
			},
			{
				"fieldname": "street_number",
				"fieldtype": "Data",
				"label": "Number",
				"insert_after": "general_info_address_sb",
			},
			{
				"fieldname": "street",
				"fieldtype": "Data",
				"label": "Street",
				"insert_after": "street_number",
			},
			{
				"fieldname": "general_info_cb3",
				"fieldtype": "Column Break",
				"insert_after": "street",
			},
			{
				"fieldname": "postal_code",
				"fieldtype": "Data",
				"label": "Postal Code",
				"insert_after": "general_info_cb3",
			},
			{
				"fieldname": "city",
				"fieldtype": "Data",
				"label": "City",
				"insert_after": "postal_code",
			},
			{
				"fieldname": "address_country",
				"fieldtype": "Link",
				"label": "Country",
				"options": "Country",
				"insert_after": "city",
			},
		]
	}
	create_custom_fields(custom_fields, ignore_validate=True, update=True)


def import_reference_data(doctype_name, json_filename, module_folder):
	json_path = os.path.join(
		os.path.dirname(os.path.abspath(__file__)),
		"configuration",
		"doctype",
		module_folder,
		"data",
		json_filename,
	)
	if not os.path.exists(json_path):
		return

	with open(json_path, "r", encoding="utf-8") as f:
		records = frappe.parse_json(f.read())

	for row in records:
		code_val = row.get("code")
		if not code_val:
			continue
		if not frappe.db.exists(doctype_name, code_val):
			doc = frappe.get_doc(
				{
					"doctype": doctype_name,
					"code": code_val,
					"label": row.get("label", ""),
				}
			)
			doc.insert(ignore_permissions=True)


def after_install():
	force_reload_custom_workspaces()
	fix_workspace_hierarchy()
	dedupe_home_links()
	import_pct_chart_of_accounts()
	install_company_custom_fields()
	import_reference_data("Legal Form", "legal_form.json", "legal_form")
	import_reference_data("Business Activity", "business_activity.json", "business_activity")
	import_reference_data("Convention", "convention.json", "convention")


def after_migrate():
	force_reload_custom_workspaces()
	fix_workspace_hierarchy()
	dedupe_home_links()
	import_pct_chart_of_accounts()
	install_company_custom_fields()
	import_reference_data("Legal Form", "legal_form.json", "legal_form")
	import_reference_data("Business Activity", "business_activity.json", "business_activity")
	import_reference_data("Convention", "convention.json", "convention")


