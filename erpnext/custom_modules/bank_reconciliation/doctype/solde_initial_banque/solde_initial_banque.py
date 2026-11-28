# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Solde Initial Banque — the statement-side opening balance of one bank
account for one Exercice, as printed on the releve (mois + sens).

One row per (Exercice, Compte de banque): the Rapprochement Manuel screen
and the Bank Reconciliation Statement read it; set_solde_initial in
rapprochement_api.py writes it (upsert). Uniqueness is enforced here in the
controller — a DB constraint cannot span two columns — and the autoname
makes the row easy to find (SIB-<exercice>-<account>).
"""

import frappe
from frappe import _
from frappe.model.document import Document


class SoldeInitialBanque(Document):
	# pylint: disable=no-member
	def validate(self) -> None:
		self.validate_unique_per_exercice_and_account()
		self.validate_account_is_bank()

	def validate_unique_per_exercice_and_account(self) -> None:
		existing = frappe.get_all(
			"Solde Initial Banque",
			filters={
				"exercice": self.exercice,
				"account": self.account,
				"name": ("!=", self.name),
			},
			limit=1,
		)
		if existing:
			frappe.throw(
				_("Un solde initial existe deja pour le compte {0} sur l'exercice {1}: {2}.").format(
					frappe.bold(self.account), frappe.bold(self.exercice), frappe.bold(existing[0].name)
				)
			)

	def validate_account_is_bank(self) -> None:
		account_type = frappe.db.get_value("Chart of Account", self.account, "account_type")
		if account_type != "Bank":
			frappe.throw(
				_("Le compte {0} n'est pas un compte de banque (type: {1}).").format(
					frappe.bold(self.account), frappe.bold(account_type or "—")
				)
			)
