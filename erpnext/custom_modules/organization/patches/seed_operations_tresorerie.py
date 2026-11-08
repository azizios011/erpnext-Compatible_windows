# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe

# Axeane's Societe nomenclature. The Investissement and Financement lists
# are the standard four cash-flow lines each and may differ from Axeane.
SEEDS = {
	"Exploitation": [
		"Encaissement recus des clients",
		"Sommes verses aux fournisseurs et au personnel",
		"Interets payes",
		"Impots sur les benefices payes",
		"Alimentation caisse",
		"Virement interne",
		"Impots et Taxes",
		"Remboursement Emprunt",
		"Placement",
		"Frais bancaire",
		"Cautionnement",
		"Encaissement suite a l'emission d'actions",
	],
	"Investissement": [
		"Decaissements provenant de l'acquisition d'immobilisations corporelles et incorporelles",
		"Encaissements provenant de la cession d'immobilisations corporelles et incorporelles",
		"Decaissements provenant de l'acquisition d'immobilisations financieres",
		"Encaissements provenant de la cession d'immobilisations financieres",
	],
	"Financement": [
		"Encaissements suite a l'emission d'actions",
		"Dividendes et autres distributions",
		"Encaissements provenant d'emprunts",
		"Remboursement d'emprunts",
	],
}


def execute():
	"""Seed the Societe operations (Personne Physique is not seeded):
	idempotent on (type_plan, categorie, libelle), never overwrites."""
	inserted = 0
	for categorie, libelles in SEEDS.items():
		for ordre, libelle in enumerate(libelles, start=1):
			if frappe.db.exists(
				"Operation Tresorerie",
				{"type_plan": "Societe", "categorie": categorie, "libelle": libelle},
			):
				continue
			frappe.get_doc(
				{
					"doctype": "Operation Tresorerie",
					"libelle": libelle,
					"categorie": categorie,
					"type_plan": "Societe",
					"visible": 1,
					"ordre": ordre,
				}
			).insert(ignore_permissions=True)
			inserted += 1

	if inserted:
		frappe.logger("axeane").info(f"seeded {inserted} Operation Tresorerie rows (Societe)")
