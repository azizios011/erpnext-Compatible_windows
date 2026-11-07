# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname

# One journal code per Facturation doctype; doctypes sharing a code share the
# same numbering series, i.e. one continuous MVT sequence per journal.
JOURNAL_BY_DOCTYPE = {
	"Facture Achat": "AC",
	"Releve Achat": "AC",
	"Facture Vente": "VT",
	"Releve Vente": "VT",
	"RS Achat": "RS",
	"RS Vente": "RS",
	"Releve Bancaire": "BQ",
	"Remise de Cheque": "BQ",
	"Virement Espece": "BQ",
	"Mensuelle": "DC",
}

# Entry doctype each Facturation document feeds in the Entries workspace
# (stage 2). The target doctypes do not exist yet; get_entry_target fails
# with a clear message until they are created.
ENTRY_DOCTYPE_BY_DOCTYPE = {
	"Facture Achat": "Payable Transaction",
	"RS Achat": "Payable Transaction",
	"Releve Achat": "Payable Transaction",
	"Facture Vente": "Receivable Transaction",
	"RS Vente": "Receivable Transaction",
	"Releve Vente": "Receivable Transaction",
	"Releve Bancaire": "Treasury Transaction",
	"Remise de Cheque": "Treasury Transaction",
	"Virement Espece": "Treasury Transaction",
	"Mensuelle": "Declaration Transaction",
}


class FacturationDocument(Document):
	"""Common base for the Facturation upload documents.

	The document name (and the read-only MVT field) is the system-given
	movement number: one numbering series per journal code, so the human
	reference stays in `reference_number` and nothing is ever asked from
	the user at naming time.
	"""

	journal_code: str = ""

	def before_naming(self):
		# The system-given number is the MVT: a client-proposed name never
		# wins. (Data imports keep their provided names, like frappe's own
		# name reset does.)
		if not frappe.flags.in_import:
			self.name = None

	def autoname(self):
		if not self.journal_code:
			frappe.throw(_("No journal code configured for {0}").format(self.doctype))
		self.name = make_autoname(f"{self.journal_code}-.YYYY.-.#####")
		self.mvt = self.name

	def validate(self):
		if self.meta.has_field("journal"):
			self.journal = self.journal_code
		if self.meta.has_field("mvt") and not self.mvt:
			self.mvt = self.name


@frappe.whitelist()
def get_entry_target(doctype: str, name: str) -> dict:
	"""Resolve the Entries-workspace target of a Facturation document.

	Returns the entry doctype, the already-linked entry (if any) and the
	defaults to prefill a new, unsaved entry form with. Nothing is written.
	"""
	if doctype not in ENTRY_DOCTYPE_BY_DOCTYPE:
		frappe.throw(_("{0} is not a Facturation document").format(doctype))

	entry_doctype = ENTRY_DOCTYPE_BY_DOCTYPE[doctype]
	if not frappe.db.exists("DocType", entry_doctype):
		frappe.throw(
			_("The Entries workspace is not available yet: doctype {0} does not exist.").format(
				entry_doctype
			)
		)

	source = frappe.get_doc(doctype, name)
	source.check_permission("read")

	defaults = {
		"source_doctype": doctype,
		"source_name": name,
		"date_operation": source.get("posting_date"),
		"ref_doc": source.get("reference_number"),
		"mvt": source.get("mvt"),
		"journal": source.get("journal") or JOURNAL_BY_DOCTYPE.get(doctype, ""),
		"company": source.get("company"),
	}
	return {
		"entry_doctype": entry_doctype,
		"existing_entry": source.get("entry") or "",
		"defaults": defaults,
	}
