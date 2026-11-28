// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// Bank Reconciliation Statement — served from custom_modules/bank_reconciliation
// (the Report record's module is re-pointed in custom_modules/setup.py), so this
// JS replaces erpnext's company/account filters with the Axeane ones: the
// Entreprise/Exercice never come from the client (require_context on the
// server), the account list is restricted to bank accounts, and the balance
// rows read bold.

frappe.query_reports["Bank Reconciliation Statement"] = {
	filters: [
		{
			fieldname: "account",
			label: __("Compte de banque"),
			fieldtype: "Link",
			options: "Chart of Account",
			reqd: 1,
			get_query() {
				return {
					filters: [["account_type", "=", "Bank"], ["is_group", "=", 0], ["disabled", "=", 0]],
				};
			},
		},
		{
			fieldname: "report_date",
			label: __("Au"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (data && column.fieldname === "statement_line" && String(value || "").indexOf(__("Solde")) === 0) {
			return `<b>${frappe.utils.escape_html(value)}</b>`;
		}
		return default_formatter(value, row, column, data);
	},
};
