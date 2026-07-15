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

# 1. Clean all files to match financial_reports.json (parent_page: "", is_hidden: 0)
all_names = ["General Accounting"] + list(tree.keys()) + [item for sublist in tree.values() for item in sublist]
for name in all_names:
    path = get_path(name)
    with open(path, 'r') as f:
        data = json.load(f)
    
    data['parent_page'] = ""
    data['is_hidden'] = 0
    
    # Remove sidebar_items from everything first
    if 'sidebar_items' in data:
        data['sidebar_items'] = []
        
    with open(path, 'w') as f:
        json.dump(data, f, indent=1)

# 2. Build the correct sidebar_items for General Accounting
ga_path = get_path("General Accounting")
with open(ga_path, 'r') as f:
    ga_data = json.load(f)

sidebar = []
for section, items in tree.items():
    # Add Section Break (equivalent to "Financial Reports" in accounting.json)
    sidebar.append({
        "child": 0,
        "collapsible": 1,
        "indent": 1,
        "keep_closed": 0,
        "label": section,
        "link_type": "Workspace",
        "link_to": section,
        "type": "Section Break"
    })
    # Add Links under it (equivalent to "Balance Sheet" in accounting.json)
    for item in items:
        sidebar.append({
            "child": 1,
            "collapsible": 1,
            "indent": 0,
            "keep_closed": 0,
            "label": item,
            "link_to": item,
            "link_type": "Workspace",
            "type": "Link"
        })

ga_data['sidebar_items'] = sidebar

with open(ga_path, 'w') as f:
    json.dump(ga_data, f, indent=1)

print("Applied standard nesting mechanism.")
