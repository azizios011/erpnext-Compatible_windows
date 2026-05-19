import frappe


FOLDER_LABEL = "Tunisian Accounting"
PLAN_COMPTABLE_LABEL = "Plan Comptable"
CHILD_WORKSPACES = ["Config", "Treatments", "States"]
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


def _upsert_icon(label: str, values: dict):
    if frappe.db.exists("Desktop Icon", label):
        frappe.db.set_value("Desktop Icon", label, values, update_modified=False)
    else:
        doc = frappe.get_doc({"doctype": "Desktop Icon", "label": label, **values})
        doc.insert(ignore_permissions=True)


def _delete_doc_if_exists(doctype: str, name: str):
    if frappe.db.exists(doctype, name):
        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)


def _remove_stale_plan_comptable_workspace():
    _delete_doc_if_exists("Workspace Sidebar", PLAN_COMPTABLE_LABEL)
    _delete_doc_if_exists("Desktop Icon", PLAN_COMPTABLE_LABEL)
    _delete_doc_if_exists("Workspace", PLAN_COMPTABLE_LABEL)

    sidebar_prefixes = [PLAN_COMPTABLE_LABEL, FOLDER_LABEL, *CHILD_WORKSPACES]
    for sidebar in frappe.get_all("Workspace Sidebar", fields=["name", "title", "for_user"]):
        title = sidebar.title or sidebar.name
        if sidebar.for_user and any(title == prefix or title.startswith(f"{prefix}-") for prefix in sidebar_prefixes):
            frappe.delete_doc("Workspace Sidebar", sidebar.name, ignore_permissions=True, force=True)


def _new_sidebar_item(label: str, link_type: str, link_to: str):
    item = frappe.new_doc("Workspace Sidebar Item")
    item.label = label
    item.type = "Link"
    item.link_type = link_type
    item.link_to = link_to
    return item


def _replace_workspace_sidebar(title: str, items: list):
    if frappe.db.exists("Workspace Sidebar", title):
        frappe.delete_doc("Workspace Sidebar", title, ignore_permissions=True, force=True)

    sidebar = frappe.new_doc("Workspace Sidebar")
    sidebar.title = title
    for item in items:
        sidebar.append("items", item)
    sidebar.insert(ignore_permissions=True)


def _ensure_folder_sidebar():
    items = []
    for workspace_name in CHILD_WORKSPACES:
        if frappe.db.exists("Workspace", workspace_name):
            items.append(_new_sidebar_item(workspace_name, "Workspace", workspace_name))

    if items:
        _replace_workspace_sidebar(FOLDER_LABEL, items)


def execute():
    _remove_stale_plan_comptable_workspace()
    _ensure_folder_sidebar()

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

    # Hide selected ERPNext workspace icons from Desk Home
    for label in HIDE_ICONS:
        if frappe.db.exists("Desktop Icon", label):
            frappe.db.set_value("Desktop Icon", label, "hidden", 1, update_modified=False)

    # Force desk cache refresh
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")

