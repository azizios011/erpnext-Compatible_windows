# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Import Configuration — one document per xlsx file type (unique target)
describing how the import hub reads it: sheet, header row, date / decimal
formats and the column map (xlsx headers -> target fields). The Grand Livre
and the Chart of Account imports read their column mapping here; Entreprise
and the Master data doctypes go through the generic engine
(organization.importing).

Grand Livre note: its columns are the READER's logical keys (date, mvt,
compte, libelle, journal, piece, debit, credit, solde, lettrage) — solde and
lettrage are recognized-but-ignored columns, the rest map onto the Ecriture
Comptable fields inside ledger_import.py."""

import frappe
from frappe import _
from frappe.model.document import Document


class ImportConfiguration(Document):
	def validate(self):
		fields = {col.target_field for col in self.columns or []}
		if not fields:
			frappe.throw(_("Configure at least one column."), title=_("Import Configuration"))
		if self.match_on and self.match_on not in fields:
			frappe.throw(
				_("Match On ({0}) doit etre le Target Field d'une colonne configuree.").format(self.match_on),
				title=_("Import Configuration"),
			)
		if cint_or_zero(self.header_row) < 0:
			frappe.throw(_("Header Row doit etre >= 0 (0 = detection automatique)."), title=_("Import Configuration"))


def cint_or_zero(value) -> int:
	try:
		return int(value or 0)
	except (TypeError, ValueError):
		return 0
