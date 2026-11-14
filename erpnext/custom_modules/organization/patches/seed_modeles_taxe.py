# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

SEEDS = [
	{
		"titre": "TVA 19%",
		"sens": "Achat et Vente",
		"lignes": [{"libelle": "TVA 19%", "type_taxe": "TVA", "taux": 19}],
	},
	{
		"titre": "TVA 13%",
		"sens": "Achat et Vente",
		"lignes": [{"libelle": "TVA 13%", "type_taxe": "TVA", "taux": 13}],
	},
	{
		"titre": "TVA 7%",
		"sens": "Achat et Vente",
		"lignes": [{"libelle": "TVA 7%", "type_taxe": "TVA", "taux": 7}],
	},
	{
		"titre": "Timbre fiscal",
		"sens": "Vente",
		"lignes": [
			{"libelle": "Timbre fiscal", "type_taxe": "Timbre fiscal", "montant": 1.0}
		],
	},
]


def execute():
	"""Seed the standard Tunisian tax models (accounts stay empty: they
	depend on the Chart of Account in use). The core Tax Template records
	are counted and left behind — their accounts are core Accounts, which
	the custom ledgers do not use."""
	for seed in SEEDS:
		if frappe.db.exists("Modele Taxe", seed["titre"]):
			continue
		frappe.get_doc({"doctype": "Modele Taxe", **seed}).insert(ignore_permissions=True)

	count = frappe.db.count("Tax Template") if frappe.db.exists("DocType", "Tax Template") else 0
	frappe.logger("axeane").info(
		f"{count} Tax Template records were not migrated: accounts are core Accounts"
	)
