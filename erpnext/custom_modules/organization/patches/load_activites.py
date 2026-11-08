# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import csv
import os

import frappe

# starter nomenclature; the full list (~703 rows) still has to be appended
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "activites.csv")


def execute():
	"""Load the Activite nomenclature from the CSV: inserts only the codes
	that do not exist yet, never overwrites an existing record — re-running
	migrate after extending the CSV inserts the missing rows."""
	with open(CSV_PATH, encoding="utf-8") as fh:
		rows = list(csv.DictReader(fh))

	inserted = 0
	for row in rows:
		code = (row.get("code") or "").strip()
		libelle = (row.get("libelle") or "").strip()
		if not code or not libelle:
			continue
		if frappe.db.exists("Activite", code):
			continue
		frappe.get_doc({"doctype": "Activite", "code": code, "libelle": libelle}).insert(
			ignore_permissions=True
		)
		inserted += 1

	if inserted:
		frappe.logger("axeane").info(f"activites: {inserted} row(s) loaded from activites.csv")
