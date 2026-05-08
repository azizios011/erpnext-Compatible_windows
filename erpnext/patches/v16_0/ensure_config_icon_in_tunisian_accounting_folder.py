import frappe


def execute():
    folder = "Tunisian Accounting"
    child = "Config"

    # Ensure folder exists
    if not frappe.db.exists("Desktop Icon", folder):
        frappe.get_doc(
            {
                "doctype": "Desktop Icon",
                "label": folder,
                "icon_type": "Folder",
                "link_type": "Workspace Sidebar",
                "hidden": 0,
                "restrict_removal": 1,
                "standard": 1,
            }
        ).insert(ignore_permissions=True)

    # Ensure Config workspace icon exists and is attached to folder
    if frappe.db.exists("Desktop Icon", child):
        frappe.db.set_value(
            "Desktop Icon",
            child,
            {
                "icon_type": "Link",
                "link_type": "Workspace Sidebar",
                "link_to": child,
                "parent_icon": folder,
                "hidden": 0,
                "restrict_removal": 1,
                "standard": 1,
            },
            update_modified=False,
        )
    else:
        frappe.get_doc(
            {
                "doctype": "Desktop Icon",
                "label": child,
                "icon_type": "Link",
                "link_type": "Workspace Sidebar",
                "link_to": child,
                "parent_icon": folder,
                "hidden": 0,
                "restrict_removal": 1,
                "standard": 1,
            }
        ).insert(ignore_permissions=True)

    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")
