import frappe

FOLDER_LABEL = "Tunisian Accounting"
CHILD_WORKSPACES = ["Config", "States", "Treatments"]
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


def _ensure_workspace_sidebar(workspace_name: str):
    if not frappe.db.exists("Workspace", workspace_name):
        return

    if frappe.db.exists("Workspace Sidebar", workspace_name):
        if workspace_name == "Config":
            frappe.delete_doc("Workspace Sidebar", workspace_name, ignore_permissions=True, force=True)
        else:
            return

    sidebar = frappe.new_doc("Workspace Sidebar")
    sidebar.title = workspace_name

    if workspace_name == "Config":
        # Do not add "Config" to its own sidebar
        item = frappe.new_doc("Workspace Sidebar Item")
        item.label = "Plan Comptable"
        item.type = "Link"
        item.link_type = "DocType"
        item.link_to = "Chart of Accounts"
        sidebar.append("items", item)

        item2 = frappe.new_doc("Workspace Sidebar Item")
        item2.label = "Chart of Accounts"
        item2.type = "URL"
        item2.url = "/app/chart-of-accounts/view/tree"
        item2.open_in_new_tab = 0
        sidebar.append("items", item2)
    else:
        item = frappe.new_doc("Workspace Sidebar Item")
        item.label = workspace_name
        item.type = "Link"
        item.link_type = "Workspace"
        item.link_to = workspace_name
        sidebar.append("items", item)

    sidebar.insert(ignore_permissions=True)


def _upsert_desktop_icon(label: str, values: dict):
    if frappe.db.exists("Desktop Icon", label):
        frappe.db.set_value("Desktop Icon", label, values, update_modified=False)
    else:
        doc = frappe.get_doc({"doctype": "Desktop Icon", "label": label, **values})
        doc.insert(ignore_permissions=True)





def apply_tunisian_accounting_desktop_layout():
    for ws_name in CHILD_WORKSPACES:
        _ensure_workspace_sidebar(ws_name)

    _upsert_desktop_icon(
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

    for ws_name in CHILD_WORKSPACES:
        _upsert_desktop_icon(
            ws_name,
            {
                "icon_type": "Link",
                "link_type": "Workspace Sidebar",
                "link_to": ws_name,
                "parent_icon": FOLDER_LABEL,
                "hidden": 0,
                "restrict_removal": 1,
                "standard": 1,
            },
        )

    for label in HIDE_ICONS:
        for icon_name in frappe.get_all("Desktop Icon", filters={"label": label}, pluck="name"):
            frappe.db.set_value("Desktop Icon", icon_name, "hidden", 1, update_modified=False)


    frappe.clear_cache()
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")

