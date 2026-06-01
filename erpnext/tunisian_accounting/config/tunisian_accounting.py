from frappe import _

def get_data():
    return [
        {
            "label": _("Tunisian Accounting"),
            "icon": "octicon octicon-repo",
            "items": [
                {
                    "type": "doctype",
                    "name": "Chart of Accounts",
                    "label": _("Chart of Accounts"),
                },
                {
                    "type": "doctype",
                    "name": "Journals Creations",
                    "label": _("Journals Creations"),
                },
                {
                    "type": "doctype",
                    "name": "Entry of Entries",
                    "label": _("Entry of Entries"),
                },
                {
                    "type": "doctype",
                    "name": "General Ledger",
                    "label": _("General Ledger"),
                },
                {
                    "type": "doctype",
                    "name": "Customer Ledger",
                    "label": _("Customer Ledger"),
                },
                {
                    "type": "doctype",
                    "name": "Supplier Ledger",
                    "label": _("Supplier Ledger"),
                },
            ]
        }
    ]
    