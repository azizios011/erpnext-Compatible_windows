import json
import os

import frappe

FOLDER_LABEL = "Tunisian Accounting"
PLAN_COMPTABLE_LABEL = "Plan Comptable"
CHILD_WORKSPACES = ["Config", "States", "Treatments"]
CONFIG_SHORTCUTS = [
    {
        "label": PLAN_COMPTABLE_LABEL,
        "type": "DocType",
        "link_to": "Chart of Accounts",
        "doc_view": "Tree",
        "color": "Blue",
    },
    {
        "label": "Fiscal Year",
        "type": "DocType",
        "link_to": "Fiscal Year",
        "doc_view": "List",
        "color": "Green",
    },
    {
        "label": "Chart of Accounts Importer",
        "type": "DocType",
        "link_to": "Chart of Accounts Importer",
        "doc_view": "List",
        "color": "Orange",
    },
    {
        "label": "Journals Creations",
        "type": "DocType",
        "link_to": "Journals Creations",
        "doc_view": "List",
        "color": "Yellow",
    },
]
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


def _ensure_config_workspace_shortcuts():
    if not frappe.db.exists("Workspace", "Config"):
        return

    shortcut_labels = [shortcut["label"] for shortcut in CONFIG_SHORTCUTS]
    for shortcut_name in frappe.get_all(
        "Workspace Shortcut",
        filters={"parent": "Config", "label": ["in", shortcut_labels]},
        pluck="name",
    ):
        frappe.delete_doc("Workspace Shortcut", shortcut_name, ignore_permissions=True, force=True)

    for idx, shortcut in enumerate(CONFIG_SHORTCUTS, start=1):
        shortcut_doc = frappe.get_doc(
            {
                "doctype": "Workspace Shortcut",
                "parent": "Config",
                "parenttype": "Workspace",
                "parentfield": "shortcuts",
                "idx": idx,
                **shortcut,
            }
        )
        shortcut_doc.insert(ignore_permissions=True)

    content = [
        {
            "id": "hdr",
            "type": "header",
            "data": {"text": '<span class="h4">Config</span>', "col": 12},
        }
    ]
    for idx, shortcut in enumerate(CONFIG_SHORTCUTS, start=1):
        content.append(
            {
                "id": f"sc{idx}",
                "type": "shortcut",
                "data": {"shortcut_name": shortcut["label"], "col": 3},
            }
        )

    frappe.db.set_value(
        "Workspace",
        "Config",
        "content",
        json.dumps(content, separators=(",", ":")),
        update_modified=False,
    )


def _new_sidebar_item(label: str, link_type: str, link_to: str = "", url: str = ""):
    item = frappe.new_doc("Workspace Sidebar Item")
    item.label = label
    item.type = "Link"
    item.link_type = link_type
    item.link_to = link_to
    if url:
        item.url = url
        item.open_in_new_tab = 0
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


def _ensure_workspace_exists(workspace_name: str):
    if frappe.db.exists("Workspace", workspace_name):
        return True

    # Try to load from JSON fixture if it doesn't exist in DB
    folder_name = workspace_name.lower().replace(" ", "_")
    file_path = frappe.get_app_path(
        "erpnext", "tunisian_accounting", "workspace", folder_name, f"{folder_name}.json"
    )

    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            doc_dict = json.load(f)
            doc_dict["doctype"] = "Workspace"
            doc = frappe.get_doc(doc_dict)
            doc.insert(ignore_permissions=True)
            return True
    return False


def _ensure_workspace_sidebar(workspace_name: str):
    if not _ensure_workspace_exists(workspace_name):
        return

    if workspace_name == "Config":
        items = []
        for shortcut in CONFIG_SHORTCUTS:
            if shortcut.get("doc_view") == "New":
                items.append(
                    _new_sidebar_item(
                        shortcut["label"],
                        "URL",
                        url="/desk/journals-creations/new-journals-creations",
                    )
                )
            else:
                items.append(_new_sidebar_item(shortcut["label"], shortcut["type"], shortcut["link_to"]))
    elif workspace_name == "Treatments":
        items = [
            _new_sidebar_item("Entry of Entries", "DocType", "Entry of Entries")
        ]
    else:
        items = [_new_sidebar_item(workspace_name, "Workspace", workspace_name)]

    _replace_workspace_sidebar(workspace_name, items)


def _upsert_desktop_icon(label: str, values: dict):
    if frappe.db.exists("Desktop Icon", label):
        frappe.db.set_value("Desktop Icon", label, values, update_modified=False)
    else:
        doc = frappe.get_doc({"doctype": "Desktop Icon", "label": label, **values})
        doc.insert(ignore_permissions=True)


def apply_tunisian_accounting_desktop_layout():
    _remove_stale_plan_comptable_workspace()

    for ws_name in CHILD_WORKSPACES:
        _ensure_workspace_exists(ws_name)

    _ensure_config_workspace_shortcuts()
    _ensure_folder_sidebar()

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





