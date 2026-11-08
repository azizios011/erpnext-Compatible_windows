# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json

import frappe


def execute():
	"""Backfill utilisateurs_json / nb_utilisateurs from assigned_staff on
	every existing Entreprise (update_modified=False, no hooks)."""
	if not frappe.db.exists("DocType", "Entreprise"):
		return

	names = frappe.get_all("Entreprise", pluck="name")
	for name in names:
		users = frappe.get_all(
			"Entreprise User",
			filters={"parent": name, "parenttype": "Entreprise"},
			fields=["user"],
			order_by="idx asc",
			pluck="user",
		)
		users = [user for user in users if user]
		frappe.db.set_value(
			"Entreprise",
			name,
			{"utilisateurs_json": json.dumps(users), "nb_utilisateurs": len(users)},
			update_modified=False,
		)
	if names:
		frappe.logger("axeane").info(f"users summary backfilled on {len(names)} Entreprise records")
