# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	"""Reshape Activite and Convention Collective from name-based rows to
	code-based ones: the libelle field takes over the old name column, and
	every record carrying a code is renamed to it (Entreprise's Link values
	follow through rename_doc's link updates). Records without a code stay
	on their old name and are logged for manual fixing."""

	# ── field renames (no-op when the doctype is already reshaped) ──
	if _has_field("Activite", "activite_name"):
		rename_field("Activite", "activite_name", "libelle")
	if _has_field("Convention Collective", "convention_name"):
		rename_field("Convention Collective", "convention_name", "libelle")

	# ── record renames to the code ──
	for doctype in ("Activite", "Convention Collective"):
		if not frappe.db.exists("DocType", doctype):
			continue
		with_code = frappe.get_all(
			doctype, filters={"code": ("is", "set")}, fields=["name", "code"]
		)
		without_code = frappe.get_all(
			doctype, filters={"code": ("is", "not set")}, pluck="name"
		)
		renamed = 0
		for row in with_code:
			if row.name == row.code:
				continue
			if frappe.db.exists(doctype, row.code):
				# a record already sits on that code: skip, never delete
				frappe.logger("axeane").info(
					f"{doctype}: code {row.code} already exists, {row.name} left as is"
				)
				continue
			frappe.rename_doc(doctype, row.name, row.code, force=True)
			renamed += 1
		if without_code:
			frappe.logger("axeane").info(
				f"{doctype}: {len(without_code)} records without a code need manual fixing: "
				+ ", ".join(without_code[:20])
			)
		frappe.logger("axeane").info(
			f"{doctype}: {renamed} record(s) renamed to their code, {len(without_code)} left without a code"
		)


def _has_field(doctype: str, fieldname: str) -> bool:
	return bool(frappe.get_meta(doctype).has_field(fieldname))
