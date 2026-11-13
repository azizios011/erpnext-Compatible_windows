# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import cint, cstr
from frappe.utils.nestedset import NestedSet

# Fields frozen on a locked (standard) account. The only allowed change on a
# locked row is the "unlock" (is_standard 1 -> 0) by an Accounts Manager in a
# save that changes nothing else — see enforce_standard_lock.
STANDARD_LOCKED_FIELDS = (
	"account_number",
	"account_name",
	"sens",
	"is_group",
	"parent_chart_of_account",
	"entreprise",
)


class ChartofAccount(NestedSet):
	def validate(self):
		self.validate_entreprise()
		self.normalize_account_number()
		self.set_classe()
		self.validate_sens()
		self.validate_parent()
		self.validate_longueur_compte()
		self.validate_duplicate_code()
		self.set_standard_flag()
		self.enforce_standard_lock()

	def validate_entreprise(self):
		"""New docs must carry the Entreprise; legacy rows predate the link and
		are left alone (the field is deliberately not reqd in the JSON)."""
		if self.is_new() and not self.entreprise:
			frappe.throw(
				_("L'entreprise est obligatoire pour un compte du plan comptable."),
				title=_("Entreprise manquante"),
			)

	def normalize_account_number(self):
		# codes are matched by prefix: whitespace removed, digits only
		number = re.sub(r"\s+", "", cstr(self.account_number))
		if not number.isdigit():
			frappe.throw(
				_("Le code du compte doit être composé de chiffres uniquement (reçu: {0}).").format(
					self.account_number or "vide"
				),
				title=_("Code invalide"),
			)
		self.account_number = number

	def set_classe(self):
		# classe = first digit of the code; rows without a valid code land in
		# "Comptes non attribués"
		self.classe = self.account_number[:1] or None

	def validate_sens(self):
		# sens (normal balance) is required on every account, Regroupements
		# included (the plan comptable file carries it on every row)
		sens = cstr(self.sens).strip().upper()
		if sens not in ("C", "D", "DC"):
			frappe.throw(
				_("Le sens est obligatoire: C (crédit), D (débit) ou DC (débit ou crédit)."),
				title=_("Sens invalide"),
			)
		self.sens = sens

	def validate_parent(self):
		"""A parent, when given, must belong to the same entreprise, be a
		Regroupement (a Comptable account can never be a parent), and its code
		must be a strict prefix of this one. One-digit codes are the class
		roots and never have a parent: a parent code would have to be shorter
		than a 1-digit code, so the prefix check below refuses them."""
		if not self.parent_chart_of_account:
			return
		parent = frappe.get_cached_doc("Chart of Account", self.parent_chart_of_account)
		if parent.entreprise != self.entreprise:
			frappe.throw(
				_("Le compte parent {0} doit appartenir à la même entreprise.").format(parent.name),
				title=_("Parent invalide"),
			)
		if not cint(parent.is_group):
			frappe.throw(
				_("Le compte parent {0} doit être un regroupement: un compte comptable ne peut jamais être un parent.").format(
					parent.name
				),
				title=_("Parent invalide"),
			)
		if len(parent.account_number) >= len(self.account_number) or not self.account_number.startswith(
			parent.account_number
		):
			frappe.throw(
				_("Le code {0} doit commencer par le code du parent {1} et être plus long.").format(
					self.account_number, parent.account_number
				),
				title=_("Parent invalide"),
			)

	def validate_longueur_compte(self):
		"""When the Entreprise fixes longueur_compte_comptable, every Comptable
		code must have exactly that length (Regroupements are free)."""
		if cint(self.is_group) or not self.entreprise:
			return
		longueur = cint(frappe.db.get_value("Entreprise", self.entreprise, "longueur_compte_comptable"))
		if longueur and len(self.account_number) != longueur:
			frappe.throw(
				_("Le code {0} doit comporter {1} chiffres (longueur des comptes définie sur l'entreprise).").format(
					self.account_number, longueur
				),
				title=_("Longueur de compte invalide"),
			)

	def validate_duplicate_code(self):
		"""The name is "<code> - <entreprise>": the same code twice for one
		entreprise would collide at insert; a clear French message instead of
		the raw DuplicateEntryError. Tolerates being called before naming."""
		if self.name and self.is_new() and frappe.db.exists(self.doctype, self.name):
			frappe.throw(
				_("Le code {0} existe déjà pour l'entreprise {1}.").format(
					self.account_number, self.entreprise
				),
				title=_("Code déjà utilisé"),
			)

	def set_standard_flag(self):
		"""Accounts created through a normal insert are never standard; the
		xlsx import (plan_comptable.py) sets is_standard itself behind
		flags.is_standard_import."""
		if self.is_new() and not self.flags.is_standard_import:
			self.is_standard = 0

	def enforce_standard_lock(self):
		"""A stored standard account cannot be modified: when the doc before
		save has is_standard = 1, any change to a STANDARD_LOCKED_FIELDS entry
		is refused. The single exception is the "unlock": an Accounts Manager
		may set is_standard 1 -> 0 in a save that changes nothing else.
		Deletion is refused in on_trash. Server code (patches, imports) can
		bypass both with self.flags.ignore_standard_lock = True."""
		if self.is_new() or self.flags.ignore_standard_lock:
			return
		previous = self.get_doc_before_save()
		if not previous or not cint(previous.is_standard):
			return
		changed = [
			fieldname
			for fieldname in STANDARD_LOCKED_FIELDS
			if cstr(previous.get(fieldname)) != cstr(self.get(fieldname))
		]
		if changed:
			frappe.throw(_("Compte standard — non modifiable"), title=_("Compte standard"))
		# nothing but is_standard changed: only an Accounts Manager may unlock
		if not cint(self.is_standard) and "Accounts Manager" not in frappe.get_roles():
			frappe.throw(_("Compte standard — non modifiable"), title=_("Compte standard"))

	def on_trash(self, allow_root_deletion=False):
		if cint(self.is_standard) and not self.flags.ignore_standard_lock:
			frappe.throw(_("Compte standard — suppression impossible"), title=_("Compte standard"))
		# keep the NestedSet bookkeeping (children check, tree update)
		super().on_trash()
