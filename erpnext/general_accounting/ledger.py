# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe.utils import flt


def fetch_entry_lines(company, from_date, to_date, party_type=None, party=None, account=None):
	"""Load ledger lines from submitted Entry of Entries (invoice) documents.

	Only submitted entries are included — draft/cancelled invoices are excluded
	from General Ledger, Customer Ledger, and Supplier Ledger in States.
	"""
	if not company:
		frappe.throw(frappe._("Company is required"))

	conditions = ["eoe.docstatus = 1", "eoe.company = %(company)s"]
	values = {"company": company}

	if from_date:
		conditions.append("eoe.posting_date >= %(from_date)s")
		values["from_date"] = from_date
	if to_date:
		conditions.append("eoe.posting_date <= %(to_date)s")
		values["to_date"] = to_date
	if party_type:
		conditions.append("detail.party_type = %(party_type)s")
		values["party_type"] = party_type
	if party:
		conditions.append("detail.party = %(party)s")
		values["party"] = party
	if account:
		conditions.append("detail.account = %(account)s")
		values["account"] = account

	query = f"""
		SELECT
			eoe.posting_date,
			eoe.name AS voucher_no,
			'Entry of Entries' AS voucher_type,
			detail.account,
			detail.party_type,
			detail.party,
			detail.debit,
			detail.credit
		FROM `tabEntry of Entries` eoe
		INNER JOIN `tabEntry of Entries Detail` detail ON detail.parent = eoe.name
		WHERE {" AND ".join(conditions)}
		ORDER BY eoe.posting_date ASC, eoe.name ASC, detail.idx ASC
	"""

	return frappe.db.sql(query, values, as_dict=True)


def with_running_balance(rows):
	balance = 0
	for row in rows:
		balance += flt(row.debit) - flt(row.credit)
		row["balance"] = balance
	return rows


def lines_to_general_ledger_detail(rows):
	return [
		{
			"posting_date": row.posting_date,
			"account": row.account,
			"voucher_type": row.voucher_type,
			"voucher_no": row.voucher_no,
			"party_type": row.party_type,
			"party": row.party,
			"debit": row.debit,
			"credit": row.credit,
			"balance": row.balance,
		}
		for row in rows
	]


def lines_to_party_ledger_detail(rows):
	return [
		{
			"posting_date": row.posting_date,
			"voucher_type": row.voucher_type,
			"voucher_no": row.voucher_no,
			"debit": row.debit,
			"credit": row.credit,
			"balance": row.balance,
		}
		for row in rows
	]
