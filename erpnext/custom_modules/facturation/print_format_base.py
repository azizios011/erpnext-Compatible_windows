# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Shared controller for the four Facturation "Print Format" parent doctypes.

One record is a named layout (layout_id + title + status) for the documents
of one Facturation sidebar section, edited as HTML/CSS or Python in the
Template Editor section. The template engine, versions and rendering arrive
in a later stage; the engine category lives here only as a plain Python
constant, not as a doctype field."""

import re

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext.custom_modules.facturation.template_validators.base import hash_editor_contents
from print_designer.tunisian_univer_engine.template_system.contract import (
	slugify,
	validate_layout_rule,
)

_SLUG_PATTERN = re.compile(r"^[0-9A-Za-z_-]+$")


class PrintFormatDocument(Document):
	# plain-Python constants for the later engine stage; not doctype fields
	CATEGORY: str = ""
	# one layout per owner: Receivable / Declaration only allow "default"
	SINGLE_LAYOUT: bool = False
	# allowed values of the category Select (the section's own documents)
	CATEGORY_OPTIONS: tuple[str, ...] = ()
	# owner fieldname(s) forming the uniqueness tuple with category and
	# layout; the fields that do not apply to the record's category drop out
	# of both the record name and the duplicate filters
	OWNER_FIELDS: tuple[str, ...] = ()
	# Payable / Receivable only: the party field that the Releve category
	# swaps for a party table, and the table's shape
	RELEVE_CATEGORY: str = ""
	RELEVE_TABLE: str = ""
	RELEVE_CHILD_DOCTYPE: str = ""
	RELEVE_CHILD_FIELD: str = ""

	def applicable_owner_fields(self) -> tuple[str, ...]:
		"""The owner fields that apply to the record's category; the form
		hides the others (depends_on) and validate clears them."""
		if self.RELEVE_CATEGORY and self.category == self.RELEVE_CATEGORY:
			return ()
		return self.OWNER_FIELDS

	def autoname(self) -> None:
		# computed here because naming runs before validate clears the
		# owner fields that do not apply to the record's category
		layout = slugify(self.layout_id or "default")
		parts = [self.category]
		parts += [self.get(fieldname) for fieldname in self.applicable_owner_fields() if self.get(fieldname)]
		parts.append(layout)
		self.name = "-".join(slugify(str(part)) for part in parts)

	def validate(self) -> None:
		self.validate_category()
		self.validate_layout()
		self.validate_owner()
		self.validate_validation_state()
		self.reject_duplicate()

	def code_hash(self) -> str:
		"""sha256 of the editor contents, the exact value the validator API
		stamps at validation time."""
		return hash_editor_contents(
			self.editor_mode, self.html_code, self.css_code, self.python_code
		)

	def validate_validation_state(self) -> None:
		"""Editing any code field invalidates the last validation; the Active
		status requires a passed validation of the exact current contents."""
		current = self.code_hash()
		if self.validated_hash and self.validated_hash != current:
			self.validation_status = "Not Validated"
		if self.status == "Active":
			if not self.validated_hash:
				frappe.throw(_("Only a passed validation can be Active; validate the template first."))
			if self.validated_hash != current:
				frappe.throw(
					_("The code changed since the last validation; validate again before activating.")
				)
			if not (self.validation_status or "").startswith("Passed"):
				frappe.throw(_("Only a passed validation can be Active; validate the template first."))

	def validate_category(self) -> None:
		if self.category not in self.CATEGORY_OPTIONS:
			frappe.throw(_("category must be one of: {0}").format(", ".join(self.CATEGORY_OPTIONS)))

	def validate_layout(self) -> None:
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
		if self.SINGLE_LAYOUT and self.layout_id != "default":
			frappe.throw(_('This section keeps one layout per owner: layout_id must be "default".'))

	def validate_owner(self) -> None:
		"""Mandatory + clearing rules of sections 2-4, enforced server side:
		owner fields that do not apply to the record's category are cleared,
		the Releve category swaps the party field for the party table."""
		applicable = self.applicable_owner_fields()
		for fieldname in self.OWNER_FIELDS:
			if fieldname not in applicable:
				self.set(fieldname, None)
		if self.RELEVE_CATEGORY:
			if self.category == self.RELEVE_CATEGORY:
				self.validate_releve_table()
				return
			self.set(self.RELEVE_TABLE, [])
		self.validate_required(*applicable)

	def validate_required(self, *fieldnames: str) -> None:
		for fieldname in fieldnames:
			if not self.get(fieldname):
				field = self.meta.get_field(fieldname)
				frappe.throw(_("{0} is required.").format(_(field.label) if field else fieldname))

	def validate_releve_table(self) -> None:
		"""The Releve party table needs at least one row, without duplicate
		rows, and each party may belong to only one record of the same
		doctype with the same category and layout_id."""
		rows = self.get(self.RELEVE_TABLE) or []
		table_label = self.meta.get_field(self.RELEVE_TABLE).label or self.RELEVE_TABLE
		if not rows:
			frappe.throw(_("{0} needs at least one row for {1}.").format(_(table_label), _(self.category)))
		seen = set()
		for row in rows:
			value = row.get(self.RELEVE_CHILD_FIELD)
			if not value:
				frappe.throw(_("Row {0}: {1} is required.").format(row.idx, _(self.RELEVE_CHILD_FIELD)))
			if value in seen:
				frappe.throw(_("Duplicate row: {0} appears more than once in {1}.").format(value, _(table_label)))
			seen.add(value)
		# conflict search joins the child rows of OTHER records of the same
		# doctype, category and layout; this record's own stored rows are
		# excluded so editing without changes never conflicts with itself
		conflicts = frappe.db.sql(
			"""
			select child.`{field}` as party, parent.name as record
			from `tab{child}` as child
			inner join `tab{parent}` as parent
				on parent.name = child.parent
			where child.parenttype = %(parenttype)s
				and child.`{field}` in %(values)s
				and parent.category = %(category)s
				and parent.layout_id = %(layout)s
				and parent.name != %(name)s
			""".format(
				child=self.RELEVE_CHILD_DOCTYPE,
				parent=self.doctype,
				field=self.RELEVE_CHILD_FIELD,
			),
			{
				"parenttype": self.doctype,
				"values": tuple(seen) or ("",),
				"category": self.category,
				"layout": self.layout_id,
				"name": self.name or "",
			},
			as_dict=True,
		)
		if conflicts:
			records = ", ".join(
				_("{0} already used in {1}").format(conflict.party, conflict.record)
				for conflict in conflicts
			)
			frappe.throw(_("Each {0} may appear in only one {1} of this category and layout: {2}.").format(
				_(self.RELEVE_CHILD_FIELD), _(self.doctype), records
			))

	def owner_filters(self) -> dict:
		"""Uniqueness tuple: category + the non-empty owner field(s) that
		apply to the record's category."""
		filters = {"category": self.category}
		filters.update({fieldname: self.get(fieldname) for fieldname in self.applicable_owner_fields() if self.get(fieldname)})
		return filters

	def reject_duplicate(self) -> None:
		duplicate = frappe.db.exists(
			self.doctype,
			{**self.owner_filters(), "layout_id": self.layout_id, "name": ("!=", self.name)},
		)
		if duplicate:
			frappe.throw(_("A print format for this category, owner and layout already exists: {0}").format(duplicate))
