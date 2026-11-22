# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Seed one Import Configuration per target (the import hub's starting
point), idempotent per target:

- Grand Livre and Chart of Account carry the column mappings the dedicated
  flows had hard-coded (reports/ledger_import.py, plan_comptable.py) — with
  these seeded the refactored readers behave exactly as before;
- Entreprise and the Master data doctypes (Forme Juridique, Convention
  Collective, Activite, Operation Tresorerie) are generated from their
  doctype meta: every non-hidden importable field with its reqd flag,
  default value and Link lookup field (the linked doctype's title field).
"""

import frappe

from erpnext.custom_modules.organization.importing import columns_for_doctype

GRAND_LIVRE_COLUMNS = [
	# the READER's logical keys (reports/ledger_import.py): solde and
	# lettrage are recognized-but-ignored columns of the source file
	{"xlsx_header": "Date", "target_field": "date", "field_type": "Date", "required": 1},
	{"xlsx_header": "Mvt", "target_field": "mvt", "field_type": "Data", "required": 1},
	{"xlsx_header": "Compte", "target_field": "compte", "field_type": "Data", "required": 1},
	{"xlsx_header": "Libelle", "target_field": "libelle", "field_type": "Data"},
	{"xlsx_header": "Journal", "target_field": "journal", "field_type": "Data", "required": 1},
	{"xlsx_header": "Piece", "target_field": "piece", "field_type": "Data"},
	{"xlsx_header": "Debit", "target_field": "debit", "field_type": "Float", "required": 1},
	{"xlsx_header": "Credit", "target_field": "credit", "field_type": "Float", "required": 1},
	{"xlsx_header": "Solde", "target_field": "solde", "field_type": "Float"},
	{"xlsx_header": "Letrage, Lettage, Lettrage", "target_field": "lettrage", "field_type": "Data"},
]

CHART_OF_ACCOUNT_COLUMNS = [
	{"xlsx_header": "Code", "target_field": "code", "field_type": "Data", "required": 1},
	{"xlsx_header": "Libelle", "target_field": "libelle", "field_type": "Data", "required": 1},
	{"xlsx_header": "Nature", "target_field": "nature", "field_type": "Select", "required": 1},
	{"xlsx_header": "Sens", "target_field": "sens", "field_type": "Select", "required": 1},
]

# the generic targets: match_on is the doctype's natural key (its autoname
# field when one exists); Grand Livre is a bulk insert (no upsert key) and
# Chart of Account matches on the account code
CONFIGS = {
	"Grand Livre": {
		"sheet_name": "",
		"header_row": 0,  # auto-detect (preamble-tolerant, as the reader always was)
		"match_on": "",
		"columns": GRAND_LIVRE_COLUMNS,
	},
	"Chart of Account": {
		"sheet_name": "",  # every sheet is a class
		"header_row": 0,  # auto-detect per sheet
		"match_on": "code",
		"columns": CHART_OF_ACCOUNT_COLUMNS,
	},
	"Entreprise": {"match_on": "code", "from_doctype": "Entreprise"},
	"Forme Juridique": {"match_on": "forme_juridique_name", "from_doctype": "Forme Juridique"},
	"Convention Collective": {"match_on": "code", "from_doctype": "Convention Collective"},
	"Activite": {"match_on": "code", "from_doctype": "Activite"},
	"Operation Tresorerie": {"match_on": "libelle", "from_doctype": "Operation Tresorerie"},
}


def execute():
	for target, spec in CONFIGS.items():
		if frappe.db.exists("Import Configuration", {"target": target}):
			continue  # idempotent: never touch an existing configuration
		if "from_doctype" in spec:
			columns = columns_for_doctype(spec["from_doctype"])
		else:
			columns = spec["columns"]
		if not columns:
			continue
		frappe.get_doc(
			{
				"doctype": "Import Configuration",
				"target": target,
				"enabled": 1,
				"sheet_name": spec.get("sheet_name") or "",
				"header_row": spec.get("header_row") or 1,
				"date_format": "dd/mm/yyyy",
				"decimal_separator": ".",
				"match_on": spec.get("match_on") or "",
				"on_duplicate": "Skip",
				"columns": columns,
			}
		).insert(ignore_permissions=True)
