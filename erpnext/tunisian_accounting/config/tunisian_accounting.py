from frappe import _

def get_data():
    return [
        {
            "label": _("Tunisian Accounting"),
            "icon": "octicon octicon-repo",
            "items": [
                {
                    "type": "doctype",
                    "name": "Journal Entry",
                    "label": _("Journal Entry"),
                    "description": _("Accounting journal entries"),
                },
                {
                    "type": "doctype",
                    "name": "Payment Entry",
                    "label": _("Payment Entry"),
                },
                {
                    "type": "doctype",
                    "name": "Account",
                    "label": _("Chart of Accounts"),
                },
            ]
        }
    ]
