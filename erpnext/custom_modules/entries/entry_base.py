# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import flt, getdate

from erpnext.custom_modules.facturation.facturation_base import ENTRY_DOCTYPE_BY_DOCTYPE

LEDGER_DOCTYPE = "Ecriture Comptable"

# Totals must match within this tolerance: TND carries three decimals.
BALANCE_TOLERANCE = 0.001

# Default Journal per entry doctype. The Journal docname IS the journal code,
# and the code doubles as the numbering-series prefix shared with the
# Facturation documents of the same journal, so the MVT sequence per journal
# stays continuous across documents and standalone entries.
JOURNAL_CODE_BY_DOCTYPE = {
	"Payable Transaction": "AC",
	"Receivable Transaction": "VT",
	"Treasury Transaction": "BQ",
	"Declaration Transaction": "DC",
}


class EntryDocument(Document):
	"""Common base for the four Entries documents.

	Saving an entry IS posting it: every save rewrites this entry's rows in
	the Ecriture Comptable ledger and marks the source Facturation document
	Comptabilisee. Entries work fully without a source document too.
	"""

	def before_naming(self):
		# the entry's name follows the movement number: the source's MVT when
		# it is linked to a Facturation document, otherwise the next number of
		# the journal's shared series
		if not frappe.flags.in_import:
			self.name = None
		self.mvt = self.resolve_mvt()

	def resolve_mvt(self) -> str:
		if self.source_doctype and self.source_name:
			self.validate_source_doctype()
			mvt = frappe.db.get_value(self.source_doctype, self.source_name, "mvt")
			if not mvt:
				frappe.throw(
					_("The source document {0} {1} has no MVT yet; save it first.").format(
						self.source_doctype, self.source_name
					)
				)
			return mvt
		journal_code = JOURNAL_CODE_BY_DOCTYPE.get(self.doctype, "OD")
		return make_autoname(f"{journal_code}-.YYYY.-.#####")

	def validate_source_doctype(self):
		"""Only Facturation documents may drive an entry's MVT and writeback."""
		if ENTRY_DOCTYPE_BY_DOCTYPE.get(self.source_doctype) != self.doctype:
			frappe.throw(
				_("{0} documents do not take sources from {1}.").format(self.doctype, self.source_doctype)
			)

	def autoname(self):
		self.name = self.mvt

	def validate(self):
		self.set_missing_values()
		self.validate_lines()
		self.validate_single_entry_per_source()
		self.apply_libelle()
		self.compute_totals()
		self.derive_period()

	def set_missing_values(self):
		if not self.journal:
			self.journal = JOURNAL_CODE_BY_DOCTYPE.get(self.doctype)
		if self.source_doctype and self.source_name:
			self.validate_source_doctype()
			if not self.ref_doc:
				self.ref_doc = (
					frappe.db.get_value(self.source_doctype, self.source_name, "reference_number") or ""
				)
			if not self.company:
				self.company = frappe.db.get_value(self.source_doctype, self.source_name, "company")

	def validate_lines(self):
		if not self.lines or len(self.lines) < 2:
			frappe.throw(_("An entry needs at least two lines (one debit, one credit)."))
		for i, line in enumerate(self.lines, start=1):
			if not line.account:
				frappe.throw(_("Line {0}: the account is mandatory.").format(i))
			debit, credit = flt(line.debit), flt(line.credit)
			if debit > 0 and credit > 0:
				frappe.throw(_("Line {0}: set a debit or a credit, not both.").format(i))
			if debit == 0 and credit == 0:
				frappe.throw(_("Line {0}: enter an amount on the debit or the credit side.").format(i))

	def validate_single_entry_per_source(self):
		if not (self.source_doctype and self.source_name):
			return
		exists = frappe.db.exists(
			self.doctype,
			{
				"source_doctype": self.source_doctype,
				"source_name": self.source_name,
				"name": ["!=", self.name or ""],
			},
		)
		if exists:
			frappe.throw(
				_("{0} already has an entry: {1}. Edit that entry instead (one entry per document).").format(
					f"{self.source_doctype} {self.source_name}", exists
				)
			)

	def apply_libelle(self):
		if self.apply_libelle_to_lines and self.libelle:
			for line in self.lines:
				line.libelle = self.libelle

	def compute_totals(self):
		self.total_debit = flt(sum(flt(line.debit) for line in self.lines), 3)
		self.total_credit = flt(sum(flt(line.credit) for line in self.lines), 3)
		self.solde = flt(self.total_debit - self.total_credit, 3)
		if abs(self.total_debit - self.total_credit) > BALANCE_TOLERANCE:
			frappe.throw(
				_("The entry is not balanced: total debit {0} vs total credit {1}.").format(
					frappe.bold(f"{self.total_debit:,.3f}"), frappe.bold(f"{self.total_credit:,.3f}")
				)
			)

	def derive_period(self):
		if self.date_operation:
			date = getdate(self.date_operation)
			self.mois = f"{date.month:02d}"
			self.jour = date.day

	def on_update(self):
		self.validate_ledger_not_lettered()
		# every save re-posts: editing a posted entry rewrites its ledger rows
		self.post_to_ledger()

	def validate_ledger_not_lettered(self):
		"""Re-posting deletes and recreates this entry's ledger rows, which
		would destroy any lettrage/pointage the accountant already made."""
		flagged = frappe.db.exists(
			LEDGER_DOCTYPE,
			{
				"source_entry_doctype": self.doctype,
				"source_entry": self.name,
				"lettrage_status": ("!=", "Non lettre"),
			},
		) or frappe.db.exists(
			LEDGER_DOCTYPE, {"source_entry_doctype": self.doctype, "source_entry": self.name, "pointe": 1}
		)
		if flagged:
			frappe.throw(_("Ecriture lettree ou pointee: delettrer d'abord"))

	def post_to_ledger(self):
		frappe.db.delete(LEDGER_DOCTYPE, {"source_entry_doctype": self.doctype, "source_entry": self.name})
		period = getdate(self.date_operation) if self.date_operation else None
		for line in self.lines:
			frappe.get_doc(
				{
					"doctype": LEDGER_DOCTYPE,
					"posting_date": self.date_operation,
					"journal": self.journal,
					"mvt": self.mvt,
					"account": line.account,
					"libelle": line.libelle,
					"debit": line.debit,
					"credit": line.credit,
					"company": self.company,
					"devise": self.devise,
					"ref_doc": self.ref_doc or "",
					"tresorerie": line.tresorerie or "",
					"lettrage": "",
					"mois": period.month if period else None,
					"annee": period.year if period else None,
					"source_entry_doctype": self.doctype,
					"source_entry": self.name,
					"source_doctype": self.source_doctype or "",
					"source_name": self.source_name or "",
				}
			).insert(ignore_permissions=True)

		if self.meta.has_field("status"):
			self.status = "Comptabilise"
			frappe.db.set_value(self.doctype, self.name, "status", "Comptabilise", update_modified=False)

		self.write_back_source()

	def write_back_source(self):
		if not (self.source_doctype and self.source_name):
			return
		if self.source_doctype not in ENTRY_DOCTYPE_BY_DOCTYPE:
			return
		# frappe.db.set_value fires no hooks: the source doc is only stamped
		frappe.db.set_value(
			self.source_doctype,
			self.source_name,
			{"entry": self.name, "entry_doctype": self.doctype, "entry_status": "Comptabilisee"},
			update_modified=False,
		)

	def on_trash(self):
		self.validate_ledger_not_lettered()
		frappe.db.delete(LEDGER_DOCTYPE, {"source_entry_doctype": self.doctype, "source_entry": self.name})
		if not (self.source_doctype and self.source_name):
			return
		if self.source_doctype not in ENTRY_DOCTYPE_BY_DOCTYPE:
			return
		frappe.db.set_value(
			self.source_doctype,
			self.source_name,
			{"entry": None, "entry_doctype": None, "entry_status": "Non saisie"},
			update_modified=False,
		)
