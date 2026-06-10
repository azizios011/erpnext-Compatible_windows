import frappe

TUNISIAN_SIDEBAR_TITLES = ("Tunisian Accounting", "Config", "States", "Treatments")


def extend_bootinfo(bootinfo):
	"""Ensure Tunisian Accounting workspace sidebars are present in desk boot data."""
	sidebars = bootinfo.get("workspace_sidebar_item")
	if sidebars is None:
		return

	for title in TUNISIAN_SIDEBAR_TITLES:
		key = title.lower()
		if sidebars.get(key):
			continue
		if not frappe.db.exists("Workspace Sidebar", title):
			continue

		sidebar = frappe.get_doc("Workspace Sidebar", title)
		sidebars[key] = {
			"label": title,
			"items": [item.as_dict(convert_dates_to_str=True) for item in sidebar.items],
			"header_icon": sidebar.header_icon,
			"module": sidebar.module,
			"app": sidebar.app,
		}
