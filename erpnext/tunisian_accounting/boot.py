import frappe

TUNISIAN_SIDEBAR_TITLES = ("Tunisian Accounting", "Config", "States", "Treatments")


def extend_bootinfo(bootinfo):
	"""Ensure Tunisian Accounting workspace sidebars are present in desk boot data."""
	sidebars = bootinfo.get("workspace_sidebar_item")
	if sidebars is None:
		return

	for title in TUNISIAN_SIDEBAR_TITLES:
		if sidebars.get(title):
			continue
		if not frappe.db.exists("Workspace Sidebar", title):
			continue

		sidebar = frappe.get_doc("Workspace Sidebar", title)
		sidebars[title] = {
			"items": [item.as_dict(convert_dates_to_str=True) for item in sidebar.items]
		}
