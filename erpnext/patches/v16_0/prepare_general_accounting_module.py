import frappe


def execute():
	"""Clear cached module maps and rebuild so General Accounting resolves after modules.txt rename."""
	frappe.cache.delete_value("app_modules")
	frappe.cache.delete_value("installed_app_modules")
	frappe.setup_module_map(include_all_apps=False)
