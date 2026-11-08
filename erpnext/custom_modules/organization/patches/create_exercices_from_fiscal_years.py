# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe


def execute():
	"""Create an Exercice per (Entreprise, enabled core Fiscal Year) with the
	Fiscal Year's dates and status Ouvert, skipping existing ones. The core
	Fiscal Year records themselves are not modified or deleted."""
	if not frappe.db.exists("DocType", "Exercice"):
		return

	entreprises = frappe.get_all("Entreprise", pluck="name")
	fiscal_years = frappe.get_all(
		"Fiscal Year",
		filters={"disabled": 0},
		fields=["name", "year", "year_start_date", "year_end_date"],
		order_by="year_start_date asc",
	)

	created = 0
	for entreprise in entreprises:
		for fiscal_year in fiscal_years:
			annee = fiscal_year.year
			if frappe.db.exists("Exercice", {"entreprise": entreprise, "annee": annee}):
				continue
			frappe.get_doc(
				{
					"doctype": "Exercice",
					"entreprise": entreprise,
					"annee": annee,
					"date_debut": fiscal_year.year_start_date,
					"date_fin": fiscal_year.year_end_date,
					"status": "Ouvert",
				}
			).insert(ignore_permissions=True)
			created += 1

	if created:
		frappe.logger("axeane").info(f"created {created} Exercice records from core Fiscal Years")
