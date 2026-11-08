# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Backfill the Entreprise/Exercice scope on existing records.

The dock "Contexte comptable" is the only source for new records; old rows
carry no Entreprise and would be invisible under the scoping. Idempotent:
only rows with an empty entreprise are touched, re-runs are no-ops.

Rule: when exactly ONE Entreprise exists it is used for every record,
otherwise the record is left unassigned (and counted in the log — it stays
invisible under scoping until fixed manually). The Exercice is that
Entreprise's Exercice whose date_debut..date_fin contains the record's own
date; left empty (and logged) when none matches. Ledger rows take their
values from their entry first, the single-Entreprise rule second.
"""

import frappe
from frappe.utils import getdate

from erpnext.custom_modules.organization.context import SCOPED_DOCTYPES

LEDGER_DOCTYPE = "Ecriture Comptable"

# the date the Exercice must contain, per doctype
DATE_FIELD_BY_DOCTYPE = {
	"Payable Transaction": "date_operation",
	"Receivable Transaction": "date_operation",
	"Treasury Transaction": "date_operation",
	"Declaration Transaction": "date_operation",
	"Lettrage Groupe": "date",
}


def execute():
	logger = frappe.logger("axeane")
	entreprise_names = frappe.get_all("Entreprise", pluck="name")
	single = entreprise_names[0] if len(entreprise_names) == 1 else ""

	if not single:
		# zero or several Entreprises: leave everything, log the counts —
		# guessing would silently move records into the wrong company
		for doctype in SCOPED_DOCTYPES:
			if not frappe.db.exists("DocType", doctype):
				continue
			count = frappe.db.count(doctype, {"entreprise": ("is", "not set")})
			if count:
				logger.info(
					f"assign_entreprise_exercice: {doctype}: {count} record(s) left unassigned "
					"({0} Entreprise(s) exist)".format(len(entreprise_names))
				)
		return

	for doctype in SCOPED_DOCTYPES:
		if doctype == LEDGER_DOCTYPE or not frappe.db.exists("DocType", doctype):
			continue
		date_field = DATE_FIELD_BY_DOCTYPE.get(doctype, "posting_date")
		rows = frappe.get_all(
			doctype,
			filters={"entreprise": ("is", "not set")},
			fields=["name", date_field],
		)
		missing = 0
		for row in rows:
			exercice = _exercice_for(single, row.get(date_field))
			if not exercice:
				missing += 1
			frappe.db.set_value(
				doctype,
				row.name,
				{"entreprise": single, "exercice": exercice},
				update_modified=False,
			)
		if rows:
			logger.info(
				f"assign_entreprise_exercice: {doctype}: {len(rows)} record(s) assigned to {single}, "
				f"{missing} without a matching Exercice"
			)

	# the ledger copies its entry's context first; standalone rows fall back
	# to the single-Entreprise rule
	if not frappe.db.exists("DocType", LEDGER_DOCTYPE):
		return
	rows = frappe.get_all(
		LEDGER_DOCTYPE,
		filters={"entreprise": ("is", "not set")},
		fields=["name", "source_entry_doctype", "source_entry", "posting_date"],
	)
	unassigned = 0
	for row in rows:
		entreprise = exercice = ""
		if row.source_entry_doctype and row.source_entry:
			entreprise, exercice = frappe.db.get_value(
				row.source_entry_doctype, row.source_entry, ["entreprise", "exercice"]
			) or ("", "")
		if not entreprise and single:
			entreprise = single
			exercice = _exercice_for(single, row.posting_date)
		if entreprise:
			frappe.db.set_value(
				LEDGER_DOCTYPE,
				row.name,
				{"entreprise": entreprise, "exercice": exercice},
				update_modified=False,
			)
		else:
			unassigned += 1
	if rows:
		logger.info(
			f"assign_entreprise_exercice: {LEDGER_DOCTYPE}: {len(rows) - unassigned} row(s) assigned, "
			f"{unassigned} left unassigned"
		)


def _exercice_for(entreprise: str, date_value) -> str:
	"""The Entreprise's Exercice containing the date, or empty."""
	if not entreprise or not date_value:
		return ""
	return (
		frappe.db.get_value(
			"Exercice",
			{
				"entreprise": entreprise,
				"date_debut": ("<=", getdate(date_value)),
				"date_fin": (">=", getdate(date_value)),
			},
			"name",
		)
		or ""
	)
