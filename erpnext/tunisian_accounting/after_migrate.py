import json

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


def _ensure_workspace_sidebar(workspace_name: str):
    if not frappe.db.exists("Workspace", workspace_name):
        return

    if frappe.db.exists("Workspace Sidebar", workspace_name):
        frappe.delete_doc("Workspace Sidebar", workspace_name, ignore_permissions=True, force=True)

    sidebar = frappe.new_doc("Workspace Sidebar")
    sidebar.title = workspace_name

    item = frappe.new_doc("Workspace Sidebar Item")
    if workspace_name == "Config":
        item.label = PLAN_COMPTABLE_LABEL
        item.type = "Link"
        item.link_type = "DocType"
        item.link_to = "Chart of Accounts"
    else:
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
    _remove_stale_plan_comptable_workspace()
    _ensure_config_workspace_shortcuts()

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
