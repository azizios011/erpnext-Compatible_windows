# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Re-point the treasury bank links to the new Banque doctype.

The three treasury documents' `bank_account` pointed at the core Bank
Account doctype and the Treasury Print Format's `bank` at the core Bank;
both fields now link Banque. For every distinct old value this patch looks
for the Banque it can match — through the old Bank Account's chart of
account (the account itself, then its number, then its name) or through the
Bank's name — and re-points the rows; a value nothing matches is blanked.
Idempotent: a value that already IS a Banque name stays where it is.

It must never fail the migration: every per-doctype step is guarded
(missing table / column skipped) and every failure is logged, never raised.
"""

import frappe

TREASURY_FIELDS = (
	("Releve Bancaire", "bank_account"),
	("Remise de Cheque", "bank_account"),
	("Versement Espece", "bank_account"),
	("Treasury Print Format", "bank"),
)


def execute():
	for doctype, fieldname in TREASURY_FIELDS:
		try:
			repoint(doctype, fieldname)
		except Exception:
			frappe.log_error("axeane bank link repoint failed", frappe.get_traceback())


def repoint(doctype: str, fieldname: str) -> None:
	"""Re-point every row of one field, one distinct old value at a time."""
	if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, fieldname):
		return
	values = frappe.get_all(doctype, fields=[fieldname], distinct=True, pluck=fieldname)
	for value in values:
		if not value:
			continue
		banque = resolve_banque(value)
		if banque == value:
			continue  # already a Banque name: nothing to do
		frappe.db.set_value(doctype, {fieldname: value}, fieldname, banque or None)
	frappe.db.commit()


def resolve_banque(value: str) -> str | None:
	"""The Banque an old Bank Account / Bank value maps to, or None.

	- A value that already names a Banque stays (idempotent second run).
	- An old Bank Account matches through its chart of account: the account
	  itself, then the account number, then the account name (the Banque's
	  bank_name prefills from the account's libelle).
	- An old Bank matches through its own bank_name."""
	if frappe.db.exists("Banque", value):
		return value

	if frappe.db.exists("Bank Account", value):
		account = frappe.db.get_value("Bank Account", value, "account")
		if account and frappe.db.exists("Banque", {"account": account}):
			return frappe.db.get_value("Banque", {"account": account}, "name")
		if account:
			number, name = frappe.db.get_value(
				"Chart of Account", account, ["account_number", "account_name"]
			) or (None, None)
			if number:
				matched = frappe.get_all(
					"Banque",
					filters=[["Chart of Account", "account_number", "=", number]],
					pluck="name",
				)
				if matched:
					return matched[0]
			if name:
				matched = frappe.get_all(
					"Banque",
					filters=[["Chart of Account", "account_name", "=", name]],
					pluck="name",
				)
				if matched:
					return matched[0]

	if frappe.db.exists("Bank", value):
		bank_name = frappe.db.get_value("Bank", value, "bank_name")
		if bank_name:
			matched = frappe.get_all("Banque", filters={"bank_name": bank_name}, pluck="name")
			if matched:
				return matched[0]

	matched = frappe.get_all("Banque", filters={"bank_name": value}, pluck="name")
	if matched:
		return matched[0]
	return None
