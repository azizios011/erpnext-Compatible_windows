import frappe

from erpnext.general_accounting.after_migrate import apply_general_accounting_desktop_layout

OLD_LABEL = "Tunisian Accounting"
NEW_LABEL = "General Accounting"


def _rename_or_drop_old(doctype: str):
	if not frappe.db.exists(doctype, OLD_LABEL):
		return

	if frappe.db.exists(doctype, NEW_LABEL):
		frappe.delete_doc(doctype, OLD_LABEL, ignore_permissions=True, force=True)
	else:
		frappe.rename_doc(doctype, OLD_LABEL, NEW_LABEL, force=True)


def execute():
	_rename_or_drop_old("Module Def")
	_rename_or_drop_old("Workspace Sidebar")
	_rename_or_drop_old("Desktop Icon")

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
	apply_general_accounting_desktop_layout()
