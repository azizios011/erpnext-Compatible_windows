import frappe

from erpnext.tunisian_accounting.after_migrate import apply_tunisian_accounting_desktop_layout

OLD_LABEL = "Tunisian Accounting"
NEW_LABEL = "General Accounting"


def execute():
	if frappe.db.exists("Module Def", OLD_LABEL) and not frappe.db.exists("Module Def", NEW_LABEL):
		frappe.rename_doc("Module Def", OLD_LABEL, NEW_LABEL, force=True)

	if frappe.db.exists("Workspace Sidebar", OLD_LABEL):
		frappe.rename_doc("Workspace Sidebar", OLD_LABEL, NEW_LABEL, force=True)

	if frappe.db.exists("Desktop Icon", OLD_LABEL):
		frappe.rename_doc("Desktop Icon", OLD_LABEL, NEW_LABEL, force=True)

	for icon_name in frappe.get_all(
		"Desktop Icon",
		filters={"parent_icon": OLD_LABEL},
		pluck="name",
	):
		frappe.db.set_value("Desktop Icon", icon_name, "parent_icon", NEW_LABEL, update_modified=False)

	for doctype in frappe.get_all("DocType", filters={"module": OLD_LABEL}, pluck="name"):
		frappe.db.set_value("DocType", doctype, "module", NEW_LABEL, update_modified=False)

	for workspace in frappe.get_all("Workspace", filters={"module": OLD_LABEL}, pluck="name"):
		frappe.db.set_value("Workspace", workspace, "module", NEW_LABEL, update_modified=False)

	for sidebar in frappe.get_all("Workspace Sidebar", filters={"module": OLD_LABEL}, pluck="name"):
		frappe.db.set_value("Workspace Sidebar", sidebar, "module", NEW_LABEL, update_modified=False)

	frappe.cache.delete_value("app_modules")
	frappe.cache.delete_value("installed_app_modules")
	frappe.db.commit()
	frappe.setup_module_map(include_all_apps=False)
	apply_tunisian_accounting_desktop_layout()
