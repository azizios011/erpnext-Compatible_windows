# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# License: GNU General Public License v3. See license.txt

import calendar

import frappe
from frappe.utils import flt, getdate

MONTHS = {
	"Janvier": 1,
	"Février": 2,
	"Mars": 3,
	"Avril": 4,
	"Mai": 5,
	"Juin": 6,
	"Juillet": 7,
	"Août": 8,
	"Septembre": 9,
	"Octobre": 10,
	"Novembre": 11,
	"Décembre": 12,
}


def get_period_dates(fiscal_year, period_type, month=None):
	year = int(fiscal_year)
	if period_type == "Annuelle":
		return f"{year}-01-01", f"{year}-12-31"

	if period_type == "Trimestrielle":
		quarter = MONTHS.get(month, 1)
		quarter = ((quarter - 1) // 3) + 1
		start_month = (quarter - 1) * 3 + 1
		end_month = start_month + 2
		last_day = calendar.monthrange(year, end_month)[1]
		return f"{year}-{start_month:02d}-01", f"{year}-{end_month:02d}-{last_day:02d}"

	month_no = MONTHS.get(month or "Janvier", 1)
	last_day = calendar.monthrange(year, month_no)[1]
	return f"{year}-{month_no:02d}-01", f"{year}-{month_no:02d}-{last_day:02d}"


def _journal_code(template_title=None, naming_series=None):
	label = (template_title or naming_series or "").strip()
	if not label:
		return ""
	clean = "".join(ch for ch in label if ch.isalnum())
	return (clean[:2] or label[:2]).upper()


def _account_display(account_number, account_name, account_id):
	number = account_number or ""
	name = account_name or account_id or ""
	if number and name:
		return f"{number} {name}"
	return number or name


def fetch_entry_lines(
	company,
	from_date,
	to_date,
	account=None,
	journal_code=None,
	voucher_filter=None,
	ledger_type=None,
):
	if not company:
		frappe.throw(frappe._("Company is required"))

	conditions = ["eoe.docstatus = 1", "eoe.company = %(company)s"]
	values = {"company": company}

	if from_date:
		conditions.append("eoe.posting_date >= %(from_date)s")
		values["from_date"] = getdate(from_date)
	if to_date:
		conditions.append("eoe.posting_date <= %(to_date)s")
		values["to_date"] = getdate(to_date)
	if account:
		conditions.append("detail.account = %(account)s")
		values["account"] = account
	if journal_code:
		conditions.append("eoe.abbr = %(journal_code)s")
		values["journal_code"] = journal_code
	if voucher_filter:
		conditions.append(
			"(eoe.name LIKE %(voucher_filter)s OR IFNULL(eoe.reference_number, '') LIKE %(voucher_filter)s)"
		)
		values["voucher_filter"] = f"%{voucher_filter}%"
	if ledger_type == "Auxiliaire":
		conditions.append("IFNULL(detail.party, '') != ''")

	query = f"""
		SELECT
			detail.idx AS movement_no,
			eoe.posting_date,
			eoe.name AS voucher_no,
			IFNULL(eoe.reference_number, eoe.name) AS document_no,
			detail.account,
			acc.account_number,
			acc.account_name,
			detail.party_type,
			detail.party,
			detail.debit,
			detail.credit,
			jc.template_title,
			jc.naming_series,
			IFNULL(eoe.reference_number, detail.party) AS libelle
		FROM `tabEntry of Entries` eoe
		INNER JOIN `tabEntry of Entries Detail` detail ON detail.parent = eoe.name
		LEFT JOIN `tabAccount` acc ON acc.name = detail.account
		LEFT JOIN `tabJournals Creations` jc ON jc.name = eoe.abbr
		WHERE {" AND ".join(conditions)}
		ORDER BY eoe.posting_date ASC, eoe.name ASC, detail.idx ASC
	"""

	rows = frappe.db.sql(query, values, as_dict=True)
	for row in rows:
		row["journal_code"] = _journal_code(row.template_title, row.naming_series)
		row["account_display"] = _account_display(row.account_number, row.account_name, row.account)
		row["tresorerie"] = ""
		row["lettering"] = ""

	return rows


def lines_to_general_ledger_detail(rows):
	return [
		{
			"movement_no": row.movement_no,
			"journal_code": row.journal_code,
			"account_display": row.account_display,
			"posting_date": row.posting_date,
			"libelle": row.libelle or row.account_display,
			"tresorerie": row.tresorerie,
			"debit": row.debit,
			"credit": row.credit,
			"lettering": row.lettering,
			"document_no": row.document_no,
			"account": row.account,
			"voucher_no": row.voucher_no,
		}
		for row in rows
	]


def get_totals(rows):
	total_debit = sum(flt(row.get("debit")) for row in rows)
	total_credit = sum(flt(row.get("credit")) for row in rows)
	return {
		"total_debit": total_debit,
		"total_credit": total_credit,
		"balance": total_debit - total_credit,
	}
