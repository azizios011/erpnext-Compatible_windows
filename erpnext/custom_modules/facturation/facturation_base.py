# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import os
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import nowdate

from erpnext.custom_modules.organization.context import (
	require_context,
	validate_date_in_exercice,
	validate_exercice_open,
	validate_source_context,
)


def attachment_file_name(url: str) -> str:
	"""Value of the list column "Nom fichier": the base name of an
	attachment path ("/files/pièce.pdf?v=1" -> "pièce.pdf")."""
	if not url:
		return ""
	return os.path.basename(urlparse(url).path)


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
		# list columns filled by the system: when the piece arrived and who
		# sent it (guarded: the treasury doctypes share this base and may not
		# carry the fields)
		if self.meta.has_field("transfer_date"):
			self.transfer_date = nowdate()
		if self.meta.has_field("sent_by"):
			self.sent_by = frappe.session.user

	def validate(self):
		if self.meta.has_field("journal"):
			self.journal = self.journal_code
		if self.meta.has_field("mvt") and not self.mvt:
			self.mvt = self.name
		if self.meta.has_field("file_name"):
			# derived from the attachment: re-derived on every validate so an
			# attachment change (or removal) keeps the list column in sync
			self.file_name = attachment_file_name(self.attachment)
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


def context_annee(context: dict) -> int:
	"""The context exercice's annee (the DM's year)."""
	return frappe.db.get_value("Exercice", context.get("exercice"), "annee") or 0


def _existing_declaration(context: dict, source) -> str:
	"""The Declaration Transaction of the source Mensuelle's month: the
	Principale first, else the latest declaration of that month. Nothing is
	written here."""
	mois = source.get("period_month") or ""
	if not mois:
		return ""
	rows = frappe.get_all(
		"Declaration Transaction",
		filters={
			"entreprise": context["entreprise"],
			"exercice": context["exercice"],
			"mois": mois,
		},
		fields=["name", "type_declaration", "creation"],
		order_by="creation desc",
	)
	if not rows:
		return ""
	for row in rows:
		if row.type_declaration == "Principale":
			return row.name
	return rows[0].name


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

	if doctype == "Mensuelle":
		# the pen opens the month's Déclaration Mensuelle, not a journal-lines
		# entry: an existing DM of the month wins, otherwise the defaults
		# prefill the form and Calculer builds it
		existing_dm = _existing_declaration(context, source)
		defaults.update(
			{
				"mois": source.get("period_month") or "",
				"annee": source.get("period_year") or context_annee(context),
				"type_declaration": "Principale",
				"mensuelle": name,
				"date_operation": None,
				"ref_doc": source.get("reference_number") or "",
				"journal": None,
				"mvt": None,
			}
		)
		return {
			"entry_doctype": entry_doctype,
			"existing_entry": existing_dm,
			"defaults": defaults,
		}

	return {
		"entry_doctype": entry_doctype,
		"existing_entry": source.get("entry") or "",
		"defaults": defaults,
	}
