import json
import os
import re

base_path = "erpnext/custom_modules/general_accounting/workspace"
parent_ws = os.path.join(base_path, "general_accounting", "general_accounting.json")

# Revert parent content
with open(parent_ws, 'r') as f:
    parent_data = json.load(f)
parent_data['content'] = "[]"
with open(parent_ws, 'w') as f:
    json.dump(parent_data, f, indent=1)

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
    # lowercase, replace non-alphanumeric with underscore, strip leading/trailing underscores
    s = re.sub(r'[^a-z0-9]', '_', name.lower())
    s = re.sub(r'_+', '_', s).strip('_')
    return s

def create_ws(name, parent_page):
    slug = make_slug(name)
    folder = os.path.join(base_path, slug)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, f"{slug}.json")
    
    data = {
        "app": "erpnext",
        "charts": [],
        "content": "[]",
        "creation": "2026-07-15 12:00:00.000000",
        "custom_blocks": [],
        "docstatus": 0,
        "doctype": "Workspace",
        "for_user": "",
        "hide_custom": 0,
        "icon": "",
        "idx": 0,
        "indicator_color": "green",
        "is_hidden": 0,
        "label": name,
        "link_type": "DocType",
        "links": [],
        "modified": "2026-07-15 12:00:00.000000",
        "modified_by": "Administrator",
        "module": "General Accounting",
        "name": name,
        "number_cards": [],
        "owner": "Administrator",
        "parent_page": parent_page,
        "public": 1,
        "quick_lists": [],
        "roles": [],
        "sequence_id": 0.0,
        "shortcuts": [],
        "sidebar_items": [],
        "standard": 1,
        "title": name,
        "type": "Workspace"
    }
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=1)

# Create Level 1 and Level 2
for l1_name, l2_items in tree.items():
    create_ws(l1_name, "General Accounting")
    for l2_name in l2_items:
        create_ws(l2_name, l1_name)

