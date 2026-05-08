import frappe


HIDE_ICONS = [
    "Assets",
    "Buying",
    "Manufacturing",
    "Projects",
    "Quality",
    "Selling",
    "Stock",
    "Subcontracting",
]


def execute():
    # Hide both standard and user-owned duplicates by label
    for label in HIDE_ICONS:
        for row in frappe.get_all("Desktop Icon", filters={"label": label}, pluck="name"):
            frappe.db.set_value("Desktop Icon", row, "hidden", 1, update_modified=False)

    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")
