import json
import os

base_path = "erpnext/custom_modules/general_accounting/workspace"

tree = {
    "General Ledger Setup": [
        "Chart of Accounts", "Journals (families)", "Cash Flow", 
        "Writing Templates", "Document Types"
    ],
    "Treatments": [
        "Entry of entries", "Import of entries", "Document processing",
        "Scanned document capture", "Lettering", "Bank reconciliation",
        "Account Replacement", "Sending Documents", "Log management",
        "Tax rate management"
    ],
    "States": [
        "Log consultation", "General Ledger", "Account Query", 
        "Balance", "Conclusion", "Income statement", 
        "Cash flow statement", "Global Financial Statements"
    ]
}

def make_slug(name):
    import re
    s = re.sub(r'[^a-z0-9]', '_', name.lower())
    return re.sub(r'_+', '_', s).strip('_')

def get_path(name):
    slug = make_slug(name)
    return os.path.join(base_path, slug, f"{slug}.json")

# Update general_accounting.json sidebar items
ga_path = get_path("General Accounting")
with open(ga_path, 'r') as f:
    ga_data = json.load(f)

ga_sidebar = []
for l1_name in tree.keys():
    ga_sidebar.append({
        "child": 0,
        "collapsible": 1,
        "default_workspace": 0,
        "icon": "folder",
        "indent": 0,
        "keep_closed": 0,
        "label": l1_name,
        "link_to": l1_name,
        "link_type": "Workspace",
        "open_in_new_tab": 0,
        "show_arrow": 0,
        "type": "Link"
    })
ga_data['sidebar_items'] = ga_sidebar
with open(ga_path, 'w') as f:
    json.dump(ga_data, f, indent=1)

# Update Level 1 workspaces sidebar items
for l1_name, l2_items in tree.items():
    l1_path = get_path(l1_name)
    with open(l1_path, 'r') as f:
        l1_data = json.load(f)
        
    l1_sidebar = []
    for l2_name in l2_items:
        l1_sidebar.append({
            "child": 0,
            "collapsible": 1,
            "default_workspace": 0,
            "icon": "folder",
            "indent": 0,
            "keep_closed": 0,
            "label": l2_name,
            "link_to": l2_name,
            "link_type": "Workspace",
            "open_in_new_tab": 0,
            "show_arrow": 0,
            "type": "Link"
        })
    l1_data['sidebar_items'] = l1_sidebar
    with open(l1_path, 'w') as f:
        json.dump(l1_data, f, indent=1)

