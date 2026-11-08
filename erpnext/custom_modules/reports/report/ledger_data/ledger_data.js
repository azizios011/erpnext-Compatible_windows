// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// "Ledger Data" (Grand Livre): two views over the same filters — the flat
// LIST view and the GRILLE (rows grouped per account, styled via row_type).
// No company and no year control: the report is scoped to the dock
// context's Entreprise and Exercice, and the period is clamped to the
// Exercice's dates server-side. PDF export will come later as a backend
// service; nothing PDF-like lives in the client.

const GL_MONTHS = [
	"Janvier",
	"Fevrier",
	"Mars",
	"Avril",
	"Mai",
	"Juin",
	"Juillet",
	"Aout",
	"Septembre",
	"Octobre",
	"Novembre",
	"Decembre",
];

frappe.query_reports["Ledger Data"] = {
	filters: [
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
		// the context defines the period: default month = the current month
		// when it falls inside the Exercice, else the Exercice's first month
		const context = (window.axeane && axeane.context && axeane.context.get()) || {};
		if (context.date_debut) {
			const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
			const debut = frappe.datetime.str_to_obj(context.date_debut);
			const fin = context.date_fin ? frappe.datetime.str_to_obj(context.date_fin) : null;
			const inside = debut <= today && (!fin || today <= fin);
			const month = inside ? today.getMonth() : debut.getMonth();
			const month_filter = report.get_filter("month");
			if (month_filter) {
				month_filter.df.default = GL_MONTHS[month];
				month_filter.set_input(GL_MONTHS[month]);
			}
		}

		// the title carries the context: "MEDDEB · EX 2026"
		const set_title = () => {
			const ctx = (window.axeane && axeane.context && axeane.context.get()) || {};
			if (ctx.entreprise_label || ctx.exercice_label) {
				report.page.set_title(
					__("Ledger Data") +
						" · " +
						[ctx.entreprise_label, ctx.exercice_label].filter(Boolean).join(" · ")
				);
			}
		};
		set_title();

		// a context switch re-runs the queries (the dock re-renders the
		// route, but a cached report page would keep its old data)
		$(document)
			.off("axeane-context-changed.ledger-data")
			.on("axeane-context-changed.ledger-data", () => {
				set_title();
				frappe.query_report.refresh();
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
