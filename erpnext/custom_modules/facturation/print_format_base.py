# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Shared controller for the four Facturation "Print Format" parent doctypes.

They wrap the Document Template engine (print_designer's template_system)
per Facturation sidebar section: one record holds the admin-uploaded template
versions for one applies_to document of one party. The doctypes never touch
Frappe's core Print Format; the 3-file contract, version numbering and the
private storage layout are Document Template's, driven with the parent
doctype's own name."""

import re

import frappe
from frappe import _
from frappe.model.document import Document

from print_designer.tunisian_univer_engine.template_system.contract import (
	slugify,
	validate_layout_rule,
)

_SLUG_PATTERN = re.compile(r"^[0-9A-Za-z_-]+$")
# one layout per owner: the engine restricts vente; "other" (Declaration)
# follows the same rule at the doctype level, the contract leaves it free
_SINGLE_LAYOUT_CATEGORIES = ("vente", "other")


class PrintFormatDocument(Document):
	# the template-system category and the Facturation doctypes of the one
	# sidebar section the doctype serves; set by each subclass
	CATEGORY: str = ""
	APPLIES_TO: tuple[str, ...] = ()

	def autoname(self) -> None:
		# "<applies_to slug>-<owner_slug>-<layout_id>"; computed here because
		# naming runs before validate fills the slug fields
		layout_id = slugify(self.layout_id or "default")
		self.name = f"{slugify(self.applies_to)}-{slugify(self.owner_party)}-{layout_id}"

	def validate(self) -> None:
		if self.applies_to not in self.APPLIES_TO:
			frappe.throw(_("applies_to must be one of: {0}").format(", ".join(self.APPLIES_TO)))
		self.category = self.CATEGORY
		if not self.owner_party:
			frappe.throw(_("Owner party is required."))
		self.owner_slug = slugify(self.owner_party)
		if not _SLUG_PATTERN.match(self.owner_slug):
			frappe.throw(_("Owner party produces an invalid slug: {0}").format(self.owner_slug))
		if not self.layout_id:
			self.layout_id = "default"
		self.layout_id = slugify(self.layout_id)
		if not _SLUG_PATTERN.match(self.layout_id):
			frappe.throw(_("Layout ID produces an invalid slug: {0}").format(self.layout_id))
		try:
			validate_layout_rule(self.CATEGORY, self.layout_id)
		except ValueError as error:
			# the engine raises ValueError; surface it as a proper ValidationError
			frappe.throw(str(error))
		if self.CATEGORY in _SINGLE_LAYOUT_CATEGORIES and self.layout_id != "default":
			frappe.throw(_('This section keeps one layout per owner: layout_id must be "default".'))
		duplicate = frappe.db.exists(
			self.doctype,
			{
				"applies_to": self.applies_to,
				"owner_party": self.owner_party,
				"layout_id": self.layout_id,
				"name": ("!=", self.name),
			},
		)
		if duplicate:
			frappe.throw(
				_("A print format for this document, owner party and layout already exists: {0}").format(
					duplicate
				)
			)
		for index, row in enumerate(self.versions, 1):
			row.version_no = index
		if self.status == "Active" and not self.active_version:
			frappe.throw(_("Activate a Passed version before setting the status to Active."))
