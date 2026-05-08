import frappe


FOLDER_LABEL = "Tunisian Accounting"
CHILD_WORKSPACES = ["Tunisian Accounting Setup", "Treatments", "States"]


def _upsert_icon(label: str, values: dict):
    if frappe.db.exists("Desktop Icon", label):
        frappe.db.set_value("Desktop Icon", label, values, update_modified=False)
    else:
        doc = frappe.get_doc({"doctype": "Desktop Icon", "label": label, **values})
        doc.insert(ignore_permissions=True)


def execute():
    # Convert or create top-level icon as a folder
    _upsert_icon(
        FOLDER_LABEL,
        {
            "icon_type": "Folder",
            "link_type": "Workspace Sidebar",
            "parent_icon": None,
            "hidden": 0,
            "restrict_removal": 1,
            "standard": 1,
        },
    )

    # Ensure workspace icons are children of this folder
    for label in CHILD_WORKSPACES:
        _upsert_icon(
            label,
            {
                "icon_type": "Link",
                "link_type": "Workspace Sidebar",
                "link_to": label,
                "parent_icon": FOLDER_LABEL,
                "hidden": 0,
                "restrict_removal": 1,
                "standard": 1,
            },
        )

    # Force desk cache refresh
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")
