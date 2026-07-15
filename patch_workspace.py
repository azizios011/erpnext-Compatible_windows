import json

content = [
    {
        "id": "hdr_glsetup",
        "type": "header",
        "data": {
            "text": "<span class=\"h4\"><b>General Ledger Setup</b></span>",
            "col": 12
        }
    },
    {
        "id": "p_glsetup",
        "type": "paragraph",
        "data": {
            "text": "Chart of Accounts<br>Journals (families)<br>Cash Flow<br>Writing Templates<br>Document Types",
            "col": 12
        }
    },
    {
        "id": "hdr_treat",
        "type": "header",
        "data": {
            "text": "<span class=\"h4\"><b>Treatments</b></span>",
            "col": 12
        }
    },
    {
        "id": "p_treat",
        "type": "paragraph",
        "data": {
            "text": "Entry of entries<br>Import of entries<br>Document processing<br>Scanned document capture<br>Lettering<br>Bank reconciliation<br>Account Replacement<br>Sending Documents<br>Log management<br>Tax rate management",
            "col": 12
        }
    },
    {
        "id": "hdr_states",
        "type": "header",
        "data": {
            "text": "<span class=\"h4\"><b>States</b></span>",
            "col": 12
        }
    },
    {
        "id": "p_states",
        "type": "paragraph",
        "data": {
            "text": "Log consultation<br>General Ledger<br>Account Query<br>Balance<br>Conclusion<br>Income statement<br>Cash flow statement<br>Global Financial Statements",
            "col": 12
        }
    }
]

path = 'erpnext/custom_modules/general_accounting/workspace/general_accounting/general_accounting.json'

with open(path, 'r') as f:
    data = json.load(f)

data['content'] = json.dumps(content)

with open(path, 'w') as f:
    json.dump(data, f, indent=1)

