# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Banque — a bank of the plan comptable, bound to a class 5 account and to
its Banque journal.

The account binding shares the tiers rules (organization/tiers_accounts.py):
a Banque lives on a custom (non-standard, non-group, non-disabled) account of
the context Entreprise whose number starts with "5" (class 5) and is not
already used by another Banque. The journal must be a Banque-type journal,
active, not linked to another Banque. The RIB is validated in FORMAT only
(20 digits: 2 bank + 3 branch + 13 account + 2 key) — the mod-97 key rule
ships as rib_key() below but validate() does not enforce it yet, since the
algorithm has not been verified against a known real RIB and a wrong key
rule would reject real bank data; the IBAN is computed from the RIB with the
standard ISO 13616 mod-97-10. A second Banque may share neither the RIB nor
the journal of another."""

import json

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext.custom_modules.organization.tiers_accounts import validate_tiers_account

JOURNAL_TYPE = "Banque"
CODE_PREFIX = "BQ"


class Banque(Document):
	def validate(self):
		validate_tiers_account(self)
		validate_journal(self)
		validate_rib(self)
		# the IBAN is derived from the RIB, never typed
		self.iban = compute_iban(self.rib) if self.rib else ""
		check_duplicates(self)


def validate_journal(doc) -> None:
	"""The journal search on the form enforces the same rules; the server
	re-checks them so nothing bypasses the picker."""
	if not doc.journal:
		return  # the field is reqd: frappe reports the missing value itself
	journal = frappe.db.get_value(
		"Journal", doc.journal, ["journal_type", "disabled"], as_dict=True
	)
	if not journal:
		frappe.throw(
			_("Le journal {0} n'existe pas.").format(frappe.bold(doc.journal)),
			title=_("Journal invalide"),
		)
	if journal.journal_type != JOURNAL_TYPE:
		frappe.throw(
			_("Le journal {0} doit être un journal de type {1}.").format(
				frappe.bold(doc.journal), frappe.bold(JOURNAL_TYPE)
			),
			title=_("Journal invalide"),
		)
	if journal.disabled:
		frappe.throw(
			_("Le journal {0} est désactivé.").format(frappe.bold(doc.journal)),
			title=_("Journal invalide"),
		)


def validate_rib(doc) -> None:
	"""The RIB is exactly 20 digits (2 bank code + 3 branch + 13 account + 2
	key). The mod-97 key rule (rib_key below) is NOT enforced here: it could
	not be verified against a known real RIB yet, so validate() checks the
	format only."""
	rib = (doc.rib or "").strip() or None
	doc.rib = rib
	if not rib:
		return
	if not rib.isdigit() or len(rib) != 20:
		frappe.throw(
			_("Le RIB doit comporter exactement 20 chiffres (2 banque + 3 agence + 13 compte + 2 clé)."),
			title=_("RIB invalide"),
		)


def rib_key(rib18: str) -> str:
	"""The Tunisian RIB key: 97 - ((first 18 digits * 100) mod 97), on two
	digits. Not enforced by validate() yet — see validate_rib."""
	return f"{97 - ((int(rib18) * 100) % 97):02d}"


def compute_iban(rib: str) -> str:
	"""TN + 2 check digits (ISO 13616 mod-97-10) + the RIB."""
	rearranged = rib + "TN00"
	converted = "".join(str(int(ch, 36)) for ch in rearranged)
	check = 98 - (int(converted) % 97)
	return f"TN{check:02d}{rib}"


def check_duplicates(doc) -> None:
	"""A second Banque may share neither the RIB nor the journal of another
	(the account's uniqueness is a DB constraint on the Link field, like the
	tiers doctypes)."""
	if doc.rib and frappe.db.exists("Banque", {"rib": doc.rib, "name": ("!=", doc.name)}):
		frappe.throw(
			_("Un autre compte bancaire utilise déjà ce RIB."),
			title=_("RIB déjà utilisé"),
		)
	if doc.journal and frappe.db.exists("Banque", {"journal": doc.journal, "name": ("!=", doc.name)}):
		frappe.throw(
			_("Un autre compte bancaire utilise déjà ce journal."),
			title=_("Journal déjà utilisé"),
		)


@frappe.whitelist()
def journal_search(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int = 0,
	page_len: int = 20,
	filters: dict | None = None,
) -> list:
	"""Link search for the `journal` field of Banque: active journals of type
	Banque not already linked to another Banque."""
	if doctype != "Banque":
		frappe.throw(
			_("Ce doctype n'accepte pas de journal Banque: {0}.").format(doctype),
			frappe.PermissionError,
		)
	if isinstance(filters, str):
		filters = json.loads(filters)
	current = (filters or {}).get("current_name") or ""
	return frappe.db.sql(
		"""
		select j.name, j.journal_code, j.journal_name
		from `tabJournal` j
		where j.journal_type = %(journal_type)s
		  and j.disabled = 0
		  and (j.journal_code like %(txt)s or j.journal_name like %(txt)s)
		  and not exists (
			select 1
			from `tabBanque` b
			where b.journal = j.name and b.name != %(current)s
		  )
		order by j.journal_code asc
		limit %(start)s, %(page_len)s
		""",
		{
			"journal_type": JOURNAL_TYPE,
			"txt": f"%{txt or ''}%",
			"current": current,
			"start": int(start or 0),
			"page_len": int(page_len or 20),
		},
		as_dict=True,
	)


@frappe.whitelist()
def next_journal_code() -> dict:
	"""The next free Banque journal code: BQ1, BQ2, … after the existing BQ*
	codes (the seeded "BQ" itself carries no number)."""
	codes = frappe.get_all("Journal", filters={"journal_code": ("like", f"{CODE_PREFIX}%")}, pluck="journal_code")
	suffixes = [int(code[len(CODE_PREFIX) :]) for code in codes if code[len(CODE_PREFIX) :].isdigit()]
	return {"code": f"{CODE_PREFIX}{max(suffixes, default=0) + 1}"}


@frappe.whitelist()
def create_journal(code: str, name: str) -> dict:
	"""Create a Banque-type journal from the form's "Creer un journal" button
	(unique code) and return its name, so the form can take it."""
	if not frappe.has_permission("Journal", "create"):
		frappe.throw(_("Not permitted to create a Journal"), frappe.PermissionError)
	code = (code or "").strip()
	name = (name or "").strip()
	if not code or not name:
		frappe.throw(_("Le code et le nom du journal sont obligatoires."), title=_("Journal"))
	if frappe.db.exists("Journal", code):
		frappe.throw(
			_("Le code journal {0} existe déjà.").format(frappe.bold(code)),
			title=_("Journal"),
		)
	journal = frappe.get_doc(
		{
			"doctype": "Journal",
			"journal_code": code,
			"journal_name": name,
			"journal_type": JOURNAL_TYPE,
		}
	)
	journal.insert()
	return {"journal": journal.name}
