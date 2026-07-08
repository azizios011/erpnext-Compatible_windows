// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

const MONTHS = [
	"Janvier",
	"Février",
	"Mars",
	"Avril",
	"Mai",
	"Juin",
	"Juillet",
	"Août",
	"Septembre",
	"Octobre",
	"Novembre",
	"Décembre",
];

frappe.query_reports["Grand Livre"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "ledger_type",
			label: __("Type grand livre"),
			fieldtype: "Select",
			options: "Général\nAuxiliaire",
			default: "Général",
			reqd: 1,
		},
		{
			fieldname: "journal_code",
			label: __("Code Journal"),
			fieldtype: "Link",
			options: "Journals Creations",
		},
		{
			fieldname: "period_type",
			label: __("Période"),
			fieldtype: "Select",
			options: "Mensuelle\nTrimestrielle\nAnnuelle",
			default: "Mensuelle",
			reqd: 1,
			on_change: () => {
				setTimeout(() => update_period_filters(), 100);
			},
		},
		{
			fieldname: "month",
			label: __("Mois"),
			fieldtype: "Select",
			options: MONTHS.join("\n"),
			default: MONTHS[new Date().getMonth()],
		},
		{
			fieldname: "fiscal_year",
			label: __("Exercice"),
			fieldtype: "Select",
			options: "2026\n2025\n2024\n2023",
			default: String(new Date().getFullYear()),
			reqd: 1,
			on_change: () => {
				setTimeout(() => update_period_filters(), 100);
			},
		},
		{
			fieldtype: "Break",
		},
		{
			fieldname: "currency",
			label: __("Devise"),
			fieldtype: "Link",
			options: "Currency",
			default: "TND",
		},
		{
			fieldname: "lettering",
			label: __("Lettrage"),
			fieldtype: "Select",
			options: "\nLettré\nNon lettré",
		},
		{
			fieldname: "extract_type",
			label: __("Type Extrait"),
			fieldtype: "Select",
			options: "Tous les comptes\nCompte sélectionné",
			default: "Tous les comptes",
			reqd: 1,
		},
		{
			fieldname: "account",
			label: __("Compte"),
			fieldtype: "Link",
			options: "Account",
			depends_on: "eval:doc.extract_type == 'Compte sélectionné'",
			mandatory_depends_on: "eval:doc.extract_type == 'Compte sélectionné'",
		},
		{
			fieldname: "voucher_filter",
			label: __("Pièce comptable"),
			fieldtype: "Data",
		},
		{
			fieldtype: "Break",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			read_only: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			read_only: 1,
		},
	],

	onload(report) {
		update_period_filters();
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "debit" && data && data.debit) {
			return `<span style="color: var(--green-600)">${value}</span>`;
		}
		if (column.fieldname === "credit" && data && data.credit) {
			return `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};

function update_period_filters() {
	const report = frappe.query_report;
	if (!report) {
		return;
	}

	const period_type = report.get_filter_value("period_type");
	const fiscal_year = parseInt(report.get_filter_value("fiscal_year") || new Date().getFullYear(), 10);
	const month = report.get_filter_value("month");

	report.toggle_filter_display("month", period_type !== "Annuelle");

	if (period_type === "Annuelle") {
		report.set_filter_value("from_date", `${fiscal_year}-01-01`);
		report.set_filter_value("to_date", `${fiscal_year}-12-31`);
		return;
	}

	if (!month) {
		return;
	}

	const month_index = MONTHS.indexOf(month);
	if (month_index < 0) {
		return;
	}

	const month_no = month_index + 1;
	const last_day = new Date(fiscal_year, month_no, 0).getDate();
	report.set_filter_value("from_date", `${fiscal_year}-${String(month_no).padStart(2, "0")}-01`);
	report.set_filter_value(
		"to_date",
		`${fiscal_year}-${String(month_no).padStart(2, "0")}-${String(last_day).padStart(2, "0")}`
	);
}
