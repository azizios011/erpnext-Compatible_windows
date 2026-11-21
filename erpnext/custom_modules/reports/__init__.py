# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Reports module package: shared helpers for the ledger import feature.

The package __init__ is the cycle-free home both ledger_import and
imported_entries import from (each of those imports the other, so any of
them holding the shared guard would recreate the circular import)."""

import frappe
from frappe import _

IMPORT_ROLES = ("Accounts Manager", "System Manager")


def check_import_roles() -> None:
	"""Every Grand Livre import endpoint requires one of IMPORT_ROLES."""
	roles = frappe.get_roles(frappe.session.user)
	if not (IMPORT_ROLES[0] in roles or IMPORT_ROLES[1] in roles):
		frappe.throw(_("Not permitted to import the Grand Livre"), frappe.PermissionError)
