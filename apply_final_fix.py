import json
import os
import re

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
    s = re.sub(r'[^a-z0-9]', '_', name.lower())
    return re.sub(r'_+', '_', s).strip('_')

def get_path(name):
    slug = make_slug(name)
    return os.path.join(base_path, slug, f"{slug}.json")

# Collect all 26 child names (3 categories + 23 leaves)
children = list(tree.keys()) + [item for sublist in tree.values() for item in sublist]

for name in children:
    path = get_path(name)
    with open(path, 'r') as f:
        data = json.load(f)
    data['is_hidden'] = 1
    with open(path, 'w') as f:
        json.dump(data, f, indent=1)
    print(f"  is_hidden=1 -> {name}")

# Verify general_accounting stays is_hidden=0
ga_path = get_path("General Accounting")
with open(ga_path, 'r') as f:
    ga = json.load(f)
print(f"\nGeneral Accounting: is_hidden={ga['is_hidden']}, sidebar_items count={len(ga.get('sidebar_items', []))}")
print("Done.")
