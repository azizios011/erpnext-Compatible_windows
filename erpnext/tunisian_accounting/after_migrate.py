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
STATES_LEDGER_DOCTYPES = [
    {"label": "General Ledger", "link_to": "General Ledger", "color": "Blue"},
    {"label": "Customer Ledger", "link_to": "Customer Ledger", "color": "Green"},
    {"label": "Supplier Ledger", "link_to": "Supplier Ledger", "color": "Orange"},
]
ENTRY_OF_ENTRIES_NEW_URL = "/desk/entry-of-entries/new-entry-of-entries-1"
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
    # Delete our standard sidebar records explicitly (not just user-specific ones)
    for name in [FOLDER_LABEL, *CHILD_WORKSPACES, PLAN_COMPTABLE_LABEL]:
        _delete_doc_if_exists("Workspace Sidebar", name)

    _delete_doc_if_exists("Desktop Icon", PLAN_COMPTABLE_LABEL)
    _delete_doc_if_exists("Workspace", PLAN_COMPTABLE_LABEL)

    # Also clean up any user-specific copies
    sidebar_prefixes = [PLAN_COMPTABLE_LABEL, FOLDER_LABEL, *CHILD_WORKSPACES]
    for sidebar in frappe.get_all("Workspace Sidebar", fields=["name", "title", "for_user"]):
        title = sidebar.title or sidebar.name
        if sidebar.for_user and any(
            title == prefix or title.startswith(f"{prefix}-")
            for prefix in sidebar_prefixes
        ):
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


def _ensure_states_workspace_shortcuts():
    if not frappe.db.exists("Workspace", "States"):
        return

    shortcut_labels = [shortcut["label"] for shortcut in STATES_LEDGER_DOCTYPES]
    for shortcut_name in frappe.get_all(
        "Workspace Shortcut",
        filters={"parent": "States", "label": ["in", shortcut_labels]},
        pluck="name",
    ):
        frappe.delete_doc("Workspace Shortcut", shortcut_name, ignore_permissions=True, force=True)

    for idx, shortcut in enumerate(STATES_LEDGER_DOCTYPES, start=1):
        frappe.get_doc(
            {
                "doctype": "Workspace Shortcut",
                "parent": "States",
                "parenttype": "Workspace",
                "parentfield": "shortcuts",
                "idx": idx,
                "type": "DocType",
                "link_to": shortcut["link_to"],
                "doc_view": "List",
                "color": shortcut["color"],
                "label": shortcut["label"],
            }
        ).insert(ignore_permissions=True)

    for link_name in frappe.get_all(
        "Workspace Link",
        filters={"parent": "States"},
        pluck="name",
    ):
        frappe.delete_doc("Workspace Link", link_name, ignore_permissions=True, force=True)

    content = [
        {
            "id": "hdr",
            "type": "header",
            "data": {"text": '<span class="h4">States</span>', "col": 12},
        },
        {
            "id": "card_ledgers",
            "type": "card",
            "data": {"card_name": "Ledgers", "col": 12},
        },
    ]
    for idx, shortcut in enumerate(STATES_LEDGER_DOCTYPES, start=1):
        content.append(
            {
                "id": f"sc{idx}",
                "type": "shortcut",
                "data": {"shortcut_name": shortcut["label"], "col": 4},
            }
        )

    frappe.db.set_value(
        "Workspace",
        "States",
        "content",
        json.dumps(content, separators=(",", ":")),
        update_modified=False,
    )


def _ensure_treatments_workspace_shortcuts():
    if not frappe.db.exists("Workspace", "Treatments"):
        return

    for shortcut_name in frappe.get_all(
        "Workspace Shortcut",
        filters={"parent": "Treatments"},
        pluck="name",
    ):
        frappe.delete_doc("Workspace Shortcut", shortcut_name, ignore_permissions=True, force=True)

    frappe.get_doc(
        {
            "doctype": "Workspace Shortcut",
            "parent": "Treatments",
            "parenttype": "Workspace",
            "parentfield": "shortcuts",
            "idx": 1,
            "type": "DocType",
            "link_to": "Entry of Entries",
            "doc_view": "New",
            "color": "Blue",
            "label": "New Entry of Entries",
        }
    ).insert(ignore_permissions=True)

    content = [
        {
            "id": "hdr",
            "type": "header",
            "data": {
                "text": '<span class="h4"><b>Treatments</b></span>',
                "col": 12,
            },
        },
        {
            "id": "hdr2",
            "type": "header",
            "data": {
                "text": (
                    '<span class="h6">Create an invoice (Entry of Entries). '
                    "Submitted entries feed the ledgers in States.</span>"
                ),
                "col": 12,
            },
        },
        {
            "id": "sc1",
            "type": "shortcut",
            "data": {"shortcut_name": "New Entry of Entries", "col": 4},
        },
    ]

    frappe.db.set_value(
        "Workspace",
        "Treatments",
        "content",
        json.dumps(content, separators=(",", ":")),
        update_modified=False,
    )


def _new_sidebar_section(label: str):
    item = frappe.new_doc("Workspace Sidebar Item")
    item.label = label
    item.type = "Section Break"
    item.indent = 1
    item.collapsible = 1
    item.child = 0
    return item


def _new_sidebar_item(label: str, link_type: str, link_to: str = "", url: str = "", child: int = 0):
    item = frappe.new_doc("Workspace Sidebar Item")
    item.label = label
    item.type = "Link"
    item.link_type = link_type
    item.link_to = link_to
    item.child = child
    if url:
        item.url = url
        item.open_in_new_tab = 0
    return item


def _replace_workspace_sidebar(title: str, items: list):
    if frappe.db.exists("Workspace Sidebar", title):
        frappe.delete_doc("Workspace Sidebar", title, ignore_permissions=True, force=True)

    sidebar = frappe.new_doc("Workspace Sidebar")
    sidebar.title = title
    sidebar.standard = 1
    sidebar.app = "erpnext"
    for item in items:
        sidebar.append("items", item)
    sidebar.insert(ignore_permissions=True, ignore_links=True)


def _ensure_folder_sidebar():
    items = []
    for workspace_name in CHILD_WORKSPACES:
        if frappe.db.exists("Workspace", workspace_name):
            items.append(_new_sidebar_item(workspace_name, "Workspace", workspace_name))

    # Always create the folder sidebar so fixtures/boot can resolve it during install.
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
            doc.insert(ignore_permissions=True, ignore_links=True)
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
            _new_sidebar_item(
                "New Entry of Entries",
                "URL",
                url=ENTRY_OF_ENTRIES_NEW_URL,
            )
        ]
    elif workspace_name == "States":
        items = [_new_sidebar_section("Ledgers")]
        for shortcut in STATES_LEDGER_DOCTYPES:
            items.append(
                _new_sidebar_item(shortcut["label"], "DocType", shortcut["link_to"], child=1)
            )
    else:
        items = [_new_sidebar_item(workspace_name, "Workspace", workspace_name)]

    _replace_workspace_sidebar(workspace_name, items)


def _upsert_desktop_icon(label: str, values: dict):
    if frappe.db.exists("Desktop Icon", label):
        frappe.db.set_value("Desktop Icon", label, values, update_modified=False)
    else:
        doc = frappe.get_doc({"doctype": "Desktop Icon", "label": label, **values})
        doc.insert(ignore_permissions=True, ignore_links=True)


def apply_tunisian_accounting_desktop_layout():
    _remove_stale_plan_comptable_workspace()

    for ws_name in CHILD_WORKSPACES:
        _ensure_workspace_exists(ws_name)

    _ensure_config_workspace_shortcuts()
    _ensure_states_workspace_shortcuts()
    _ensure_treatments_workspace_shortcuts()

    for ws_name in CHILD_WORKSPACES:
        _ensure_workspace_sidebar(ws_name)

    _ensure_folder_sidebar()

    frappe.clear_cache()

    _upsert_desktop_icon(
        FOLDER_LABEL,
        {
            "icon_type": "Folder",
            "link_type": "Workspace Sidebar",
            "link_to": "",
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





