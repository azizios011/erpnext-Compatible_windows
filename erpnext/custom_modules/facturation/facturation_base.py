# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname

from erpnext.custom_modules.organization.context import (
	require_context,
	validate_date_in_exercice,
	validate_exercice_open,
	validate_source_context,
)

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
	"Versement Espece": "BQ",
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
	"Versement Espece": "Treasury Transaction",
	"Mensuelle": "Declaration Transaction",
}


class FacturationDocument(Document):
	"""Common base for the Facturation upload documents.

	The document name (and the read-only MVT field) is the system-given
	movement number: one numbering series per journal code, so the human
	reference stays in `reference_number` and nothing is ever asked from
	the user at naming time.

	The Entreprise and Exercice always come from the dock "Contexte
	comptable" (never from client input); the Exercice must be Ouvert and
	the piece date must fall inside it.
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

	def before_insert(self):
		# the context is the only source: the user never picks a company
		context = require_context()
		self.entreprise = context["entreprise"]
		self.exercice = context["exercice"]

	def validate(self):
		if self.meta.has_field("journal"):
			self.journal = self.journal_code
		if self.meta.has_field("mvt") and not self.mvt:
			self.mvt = self.name
		self.validate_context()

	def validate_context(self):
		"""The Exercice must be Ouvert and the piece date inside it; the
		record stays in the user's current Entreprise/Exercice."""
		context = require_context()
		validate_exercice_open(context)
		if self.meta.has_field("posting_date") and self.posting_date:
			validate_date_in_exercice(self.posting_date, context, _("Date piece"))
		if not self.entreprise:
			self.entreprise = context["entreprise"]
		if not self.exercice:
			self.exercice = context["exercice"]


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

	# the pen action writes into the user's context: a source from another
	# Entreprise/Exercice is refused before the form even opens
	context = require_context()
	validate_source_context(doctype, name, context)

	defaults = {
		"source_doctype": doctype,
		"source_name": name,
		"date_operation": source.get("posting_date"),
		"ref_doc": source.get("reference_number"),
		"mvt": source.get("mvt"),
		"journal": source.get("journal") or JOURNAL_BY_DOCTYPE.get(doctype, ""),
		"entreprise": context["entreprise"],
		"exercice": context["exercice"],
	}
	return {
		"entry_doctype": entry_doctype,
		"existing_entry": source.get("entry") or "",
		"defaults": defaults,
	}
