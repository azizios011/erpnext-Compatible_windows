import frappe


def execute():
    old_name_candidates = ["Accounting Setup", "Tunisian Accounting Setup", "Setup"]
    new_name = "Config"

    # Rename workspace to Config if needed
    for old_name in old_name_candidates:
        if old_name != new_name and frappe.db.exists("Workspace", old_name) and not frappe.db.exists("Workspace", new_name):
            frappe.rename_doc("Workspace", old_name, new_name, force=True, merge=False)
            break

    # Ensure Config workspace title/label are consistent
    if frappe.db.exists("Workspace", new_name):
        frappe.db.set_value(
            "Workspace",
            new_name,
            {
                "title": "Config",
                "label": "Config",
            },
            update_modified=False,
        )

    # Move Desktop Icon link/label to Config
    for old_label in old_name_candidates:
        if frappe.db.exists("Desktop Icon", old_label) and not frappe.db.exists("Desktop Icon", new_name):
            frappe.rename_doc("Desktop Icon", old_label, new_name, force=True, merge=False)
            break

    if frappe.db.exists("Desktop Icon", new_name):
        frappe.db.set_value(
            "Desktop Icon",
            new_name,
            {
                "link_to": "Config",
                "link_type": "Workspace Sidebar",
                "icon_type": "Link",
                "parent_icon": "Tunisian Accounting",
                "hidden": 0,
            },
            update_modified=False,
        )

    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")
