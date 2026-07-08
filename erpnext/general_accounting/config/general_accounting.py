from frappe import _


def get_data():
	return [
		{
			"label": _("General Accounting"),
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
					"type": "report",
					"name": "Grand Livre",
					"label": _("General Ledger"),
				},
			],
		}
	]
