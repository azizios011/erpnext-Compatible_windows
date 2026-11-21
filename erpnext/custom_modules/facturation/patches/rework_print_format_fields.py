# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Reshape the four Facturation "Print Format" doctypes created in stage 1.

The read-only engine category (achat/vente/bank/other) gives way to the
section's document Select: applies_to is renamed to category once the old
column is dropped to free its name. owner_party is retargeted per section —
supplier (Fournisseur) / client (Client) / bank (Bank) — and values that do
not exist in the new target doctype are set to NULL; Declaration drops the
column entirely. Runs pre_model_sync so the model sync finds the renamed
columns and only adds the new ones.

Every ALTER goes through frappe.db.sql_ddl (commit + execute): a raw DDL
after pending writes raises ImplicitCommitError. Each step is guarded with
frappe.db.has_column, and the NULL-out runs whenever the new column exists
(not only right after a rename), so a partial earlier run — renames kept,
data fix rolled back — converges on the next pass. Record names are left as
they are."""

import frappe

# doctype -> (old column, new column, new Link target); None when the old
# column is dropped without a replacement (Declaration)
PARTY_CHANGES = {
	"Payable Print Format": ("owner_party", "supplier", "Fournisseur"),
	"Receivable Print Format": ("owner_party", "client", "Client"),
	"Treasury Print Format": ("owner_party", "bank", "Bank"),
	"Declaration Print Format": None,
}


def execute():
	for doctype, change in PARTY_CHANGES.items():
		if not frappe.db.table_exists(doctype):
			# fresh site: the sync creates the table from the new JSON
			continue
		move_category_column(doctype)
		if change:
			rename_party_column(doctype, *change)
		elif frappe.db.has_column(doctype, "owner_party"):
			frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `owner_party`")


def move_category_column(doctype: str) -> None:
	"""applies_to becomes category; the old read-only engine category column
	is dropped first to free its name. Both Select columns are varchar(140)."""
	if not frappe.db.has_column(doctype, "applies_to"):
		return
	if frappe.db.has_column(doctype, "category"):
		# old-schema state: both columns exist, the old one must go
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` DROP COLUMN `category`")
	frappe.db.sql_ddl(
		f"ALTER TABLE `tab{doctype}` CHANGE `applies_to` `category` VARCHAR(140) DEFAULT NULL"
	)


def rename_party_column(doctype: str, old: str, new: str, target: str) -> None:
	if frappe.db.has_column(doctype, old) and not frappe.db.has_column(doctype, new):
		# owner_party was a Link, the new column is a Link: same varchar(140)
		frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` CHANGE `{old}` `{new}` VARCHAR(140) DEFAULT NULL")
	# values pointing at the old target doctype are meaningless now; a value
	# is kept only when the new target doctype really has that record. The
	# fix runs whenever the column exists, so a partial earlier run whose
	# data fix rolled back converges here.
	if frappe.db.has_column(doctype, new) and frappe.db.table_exists(target):
		frappe.db.sql(
			f"""UPDATE `tab{doctype}`
				SET `{new}` = NULL
				WHERE `{new}` IS NOT NULL
					AND `{new}` NOT IN (SELECT name FROM `tab{target}`)"""
		)
		frappe.db.commit()
