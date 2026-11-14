# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Shared account binding for the tiers doctypes (Client / Fournisseur).

A Client can only live on a custom account under 411, a Fournisseur only on a
custom account under 401 — the account must belong to the Entreprise of the
current accounting context and may not be a locked (standard) row of the plan
comptable. The same rules drive the link search the forms use."""

import json

import frappe
from frappe import _

from erpnext.custom_modules.organization.context import require_entreprise

TIERS_PREFIX = {"Client": "411", "Fournisseur": "401"}


@frappe.whitelist()
def tiers_account_search(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int = 0,
	page_len: int = 20,
	filters: dict | None = None,
) -> list:
	"""Link search for the `account` field of Client / Fournisseur: custom
	accounts under the doctype's prefix, of the context Entreprise, not used
	by another record of the same doctype."""
	if doctype not in TIERS_PREFIX:
		frappe.throw(
			_("Ce doctype n'accepte pas de compte tiers: {0}.").format(doctype),
			frappe.PermissionError,
		)
	if isinstance(filters, str):
		filters = json.loads(filters)
	current = (filters or {}).get("current_name") or ""
	prefix = TIERS_PREFIX[doctype]
	entreprise = require_entreprise()
	return frappe.db.sql(
		f"""
		select ca.name, ca.account_number, ca.account_name
		from `tabChart of Account` ca
		where ca.account_number like %(prefix)s
		  and char_length(ca.account_number) > %(plen)s
		  and ca.is_group = 0
		  and ca.is_standard = 0
		  and ca.disabled = 0
		  and ca.entreprise = %(entreprise)s
		  and (ca.account_number like %(txt)s or ca.account_name like %(txt)s)
		  and not exists (
			select 1
			from `tab{doctype}` t
			where t.account = ca.name and t.name != %(current)s
		  )
		order by ca.account_number asc
		limit %(start)s, %(page_len)s
		""",
		{
			"prefix": prefix + "%",
			"plen": len(prefix),
			"entreprise": entreprise,
			"txt": f"%{txt or ''}%",
			"current": current,
			"start": int(start or 0),
			"page_len": int(page_len or 20),
		},
		as_dict=True,
	)


@frappe.whitelist()
def compte_search(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int = 0,
	page_len: int = 20,
	filters: dict | None = None,
) -> list:
	"""Generic Chart of Account link search: non-group, non-disabled accounts
	of the context Entreprise (no prefix rule) — used by the Modele Taxe
	lines."""
	entreprise = require_entreprise()
	return frappe.db.sql(
		"""
		select ca.name, ca.account_number, ca.account_name
		from `tabChart of Account` ca
		where ca.is_group = 0
		  and ca.disabled = 0
		  and ca.entreprise = %(entreprise)s
		  and (ca.account_number like %(txt)s or ca.account_name like %(txt)s)
		order by ca.account_number asc
		limit %(start)s, %(page_len)s
		""",
		{
			"entreprise": entreprise,
			"txt": f"%{txt or ''}%",
			"start": int(start or 0),
			"page_len": int(page_len or 20),
		},
		as_dict=True,
	)


def validate_tiers_account(doc) -> None:
	"""Server-side rules for the `account` binding of Client / Fournisseur:
	custom (not standard, not disabled), non-group, under the doctype's prefix
	(411 Client / 401 Fournisseur) and longer than it, in the Entreprise of
	the current accounting context."""
	prefix = TIERS_PREFIX[doc.doctype]
	account = doc.get("account")
	if not account:
		return  # the field is reqd: frappe reports the missing value itself
	acc = frappe.db.get_value(
		"Chart of Account",
		account,
		["account_number", "is_group", "is_standard", "disabled", "entreprise"],
		as_dict=True,
	)
	if not acc:
		frappe.throw(
			_("Le compte {0} n'existe pas.").format(frappe.bold(account)),
			title=_("Compte invalide"),
		)

	number = acc.account_number or ""
	if not number.startswith(prefix) or len(number) <= len(prefix):
		frappe.throw(
			_("Le compte {0} doit être un compte personnalisé sous {1}.").format(
				frappe.bold(account), frappe.bold(prefix)
			),
			title=_("Compte invalide"),
		)
	if acc.is_group:
		frappe.throw(
			_("Le compte {0} est un regroupement: choisissez un compte comptable sous {1}.").format(
				frappe.bold(account), frappe.bold(prefix)
			),
			title=_("Compte invalide"),
		)
	if acc.is_standard:
		frappe.throw(
			_("Le compte {0} est un compte standard (verrouillé): seuls les comptes personnalisés sont autorisés.").format(
				frappe.bold(account)
			),
			title=_("Compte invalide"),
		)
	if acc.disabled:
		frappe.throw(
			_("Le compte {0} est désactivé.").format(frappe.bold(account)),
			title=_("Compte invalide"),
		)
	if acc.entreprise != require_entreprise():
		frappe.throw(
			_("Le compte {0} n'appartient pas à l'entreprise du contexte comptable.").format(
				frappe.bold(account)
			),
			title=_("Compte invalide"),
		)
