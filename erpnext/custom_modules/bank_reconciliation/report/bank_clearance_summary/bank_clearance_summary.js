// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// Bank Clearance Summary — served from custom_modules/bank_reconciliation (the
// Report record's module is re-pointed in custom_modules/setup.py). Axeane
// filters on our Ecriture Comptable ledger: the Entreprise/Exercice come from
// the dock context (never the client), the account list is bank accounts, and
// the totals ride the summary cards.

frappe.query_reports["Bank Clearance Summary"] = {
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
			fieldname: "type_ecriture",
			label: __("Type ecriture"),
			fieldtype: "Select",
			options: "Toutes\nRapprochees\nNon rapprochees",
			default: "Toutes",
		},
		{ fieldname: "from_date", label: __("Du"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Au"), fieldtype: "Date" },
		{ fieldname: "journal", label: __("Journal"), fieldtype: "Link", options: "Journal" },
		{
			fieldname: "tresorerie",
			label: __("Piece de tresorerie"),
			fieldtype: "Link",
			options: "Operation Tresorerie",
		},
		{
			fieldname: "date_rapprochement",
			label: __("Rapproche le"),
			fieldtype: "Date",
			description: __("Date de rapprochement exacte."),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (data && data.row_type === "total" && column.fieldname === "libelle") {
			return `<b>${frappe.utils.escape_html(value)}</b>`;
		}
		return default_formatter(value, row, column, data);
	},
};
