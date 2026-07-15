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

# Update Level 1 and Level 2 to is_hidden: 1
for l1_name, l2_items in tree.items():
    l1_path = get_path(l1_name)
    with open(l1_path, 'r') as f:
        data = json.load(f)
    data['is_hidden'] = 1
    with open(l1_path, 'w') as f:
        json.dump(data, f, indent=1)
        
    for l2_name in l2_items:
        l2_path = get_path(l2_name)
        with open(l2_path, 'r') as f:
            data = json.load(f)
        data['is_hidden'] = 1
        with open(l2_path, 'w') as f:
            json.dump(data, f, indent=1)

