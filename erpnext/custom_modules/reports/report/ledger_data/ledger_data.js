// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// "Ledger Data" (Grand Livre): two views over the same filters — the flat
// LIST view and the GRILLE (rows grouped per account, styled via row_type).
// PDF export will come later as a backend service; nothing PDF-like lives
// in the client.

frappe.query_reports["Ledger Data"] = {
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
			options: "General\nAuxiliaire Client\nAuxiliaire Fournisseur",
			default: "General",
			reqd: 1,
		},
		{
			fieldname: "journal",
			label: __("Code Journal"),
			fieldtype: "MultiSelectList",
			options: "Journal",
			get_data(txt) {
				return frappe.db.get_link_options("Journal", txt);
			},
		},
		{
			fieldname: "period_type",
			label: __("Periode"),
			fieldtype: "Select",
			options: "Mensuelle\nTrimestrielle\nAnnuelle\nPersonnalisee",
			default: "Mensuelle",
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Exercice"),
			fieldtype: "Select",
			options: [frappe.datetime.get_today().slice(0, 4)],
			default: frappe.datetime.get_today().slice(0, 4),
		},
		{
			fieldname: "month",
			label: __("Mois"),
			fieldtype: "Select",
			options: "Janvier\nFevrier\nMars\nAvril\nMai\nJuin\nJuillet\nAout\nSeptembre\nOctobre\nNovembre\nDecembre",
			default: "Janvier",
			reqd: 1,
			depends_on: "eval:doc.period_type == 'Mensuelle'",
		},
		{
			fieldname: "quarter",
			label: __("Trimestre"),
			fieldtype: "Select",
			options: "T1\nT2\nT3\nT4",
			default: "T1",
			depends_on: "eval:doc.period_type == 'Trimestrielle'",
		},
		{
			fieldname: "from_date",
			label: __("Du"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
		},
		{
			fieldname: "to_date",
			label: __("Au"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
		},
		{
			fieldname: "devise",
			label: __("Devise"),
			fieldtype: "Link",
			options: "Currency",
			default: "TND",
		},
		{
			fieldname: "lettrage",
			label: __("Lettrage"),
			fieldtype: "Select",
			options: "Tous\nLettre\nNon lettre",
			default: "Tous",
		},
		{
			fieldname: "extract_type",
			label: __("Type Extrait"),
			fieldtype: "Select",
			options: "Tous les comptes\nComptes mouvementes\nComptes non soldes",
			default: "Tous les comptes",
			reqd: 1,
		},
		{
			fieldname: "mvt",
			label: __("Piece comptable"),
			fieldtype: "Data",
			description: __("One or several MVT numbers, comma-separated"),
		},
		{
			// toggled by the "Vue Grille" / "Vue Liste" buttons; hidden from
			// the filter UI on purpose
			fieldname: "view",
			label: "View",
			fieldtype: "Select",
			options: "Liste\nGrille",
			default: "Liste",
			hidden: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		if (!data || !data.row_type) {
			return default_formatter(value);
		}
		const formatted = default_formatter(value);
		if (data.row_type === "header" || data.row_type === "total") {
			return `<span style="font-weight:700">${formatted}</span>`;
		}
		if (data.row_type === "opening") {
			return `<span style="font-style:italic">${formatted}</span>`;
		}
		return formatted;
	},

	onload(report) {
		// Exercice options: the years actually present in the ledger
		frappe.call({
			method: "erpnext.custom_modules.reports.report.ledger_data.ledger_data.get_ledger_years",
			args: {},
			callback(r) {
				const years = r.message && r.message.length ? r.message : [frappe.datetime.get_today().slice(0, 4)];
				const year_filter = report.get_filter("year");
				year_filter.df.options = years.join("\n");
				if (!years.includes(year_filter.df.default)) {
					year_filter.df.default = years[years.length - 1];
				}
				year_filter.refresh();
			},
		});

		let filters_visible = true;
		const set_filters_visible = (visible) => {
			filters_visible = visible;
			$(report.page.page_form).toggle(visible);
			btn_hide_filters.toggleClass("hidden", !visible);
			btn_show_filters.toggleClass("hidden", visible);
		};
		const set_grid_visible = (visible) => {
			frappe.query_report.set_filter_value("view", visible ? "Grille" : "Liste");
			if (visible && filters_visible) {
				// the Grille hides the filter section on purpose
				set_filters_visible(false);
			}
			btn_grid.toggleClass("hidden", visible);
			btn_list.toggleClass("hidden", !visible);
		};
		const btn_hide_filters = report.page.add_inner_button(__("Cacher filtres"), () =>
			set_filters_visible(false)
		);
		const btn_show_filters = report.page.add_inner_button(__("Afficher filtres"), () =>
			set_filters_visible(true)
		);
		const btn_grid = report.page.add_inner_button(__("Vue Grille"), () => set_grid_visible(true));
		const btn_list = report.page.add_inner_button(__("Vue Liste"), () => set_grid_visible(false));
		btn_show_filters.addClass("hidden");
		btn_list.addClass("hidden");
	},
};
