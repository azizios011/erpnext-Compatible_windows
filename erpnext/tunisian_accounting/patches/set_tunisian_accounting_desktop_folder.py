import frappe


def execute():
    folder_label = "Tunisian Accounting"
    workspace_labels = ["Tunisian Accounting Setup", "Treatments", "States"]

    # Ensure folder icon exists
    if not frappe.db.exists("Desktop Icon", folder_label):
        folder = frappe.get_doc(
            {
                "doctype": "Desktop Icon",
                "label": folder_label,
                "icon_type": "Folder",
                "link_type": "Workspace Sidebar",
                "hidden": 0,
                "restrict_removal": 1,
                "standard": 1,
            }
        )
        folder.insert(ignore_permissions=True)

    # Force child workspace icons under folder
    for label in workspace_labels:
        if frappe.db.exists("Desktop Icon", label):
            frappe.db.set_value(
                "Desktop Icon",
                label,
                {
                    "parent_icon": folder_label,
                    "hidden": 0,
                    "icon_type": "Link",
                    "link_type": "Workspace Sidebar",
                    "link_to": label,
                },
                update_modified=False,
            )

    frappe.db.commit()
