// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// "Ledger Data" (Grand Livre): a classic Script Report with three views over
// the same filters. The LIST view is the native report page — filters,
// datatable, and the summary cards moved to a sticky bar at the bottom. The
// PDF and XLSX views are placeholders for the OnlyOffice-based previews
// (mount / unmount stubs on frappe.query_reports["Ledger Data"].views). The
// Grille data builder stays in ledger_data.py: it will feed the PDF / XLSX
// generation later.

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
	],

	// the PDF / XLSX mounts the switcher calls: el = the wide-open container,
	// filters = the CURRENT filter values (report.get_filter_values()). The
	// real previews are built later on this contract.
	views: {
		pdf: {
			mount(el, filters) {
				el.innerHTML = "";
				el.appendChild(
					frappe.ui.empty_state({
						icon: "file-text",
						title: __("Apercu PDF, bientot disponible"),
						description: __("The PDF preview will be generated from the XLSX view."),
					})
				);
			},
			unmount() {},
		},
		xlsx: {
			mount(el, filters) {
				el.innerHTML = "";
				el.appendChild(
					frappe.ui.empty_state({
						icon: "table",
						title: __("XLSX view, coming soon"),
						description: __("The XLSX view will be generated from the same data."),
					})
				);
			},
			unmount() {},
		},
	},

	formatter(value, row, column, data, default_formatter) {
		// the MVT of the two island-backed entry doctypes opens the entry in
		// inspect mode through erpnext.entries.open_entry — in both views.
		// Header, opening and total rows carry no source_entry: default.
		if (
			column.id === "mvt" &&
			data &&
			data.source_entry &&
			["Payable Transaction", "Receivable Transaction"].includes(data.source_entry_doctype)
		) {
			return `<a href="#" class="gl-mvt-link" data-entry-doctype="${frappe.utils.escape_html(
				data.source_entry_doctype
			)}" data-entry="${frappe.utils.escape_html(data.source_entry)}">${frappe.utils.escape_html(value)}</a>`;
		}
		return default_formatter(value);
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

		// the island-backed MVT links open the entry in inspect mode
		report.$report
			.off("click.gl-mvt-link")
			.on("click.gl-mvt-link", ".gl-mvt-link", function (event) {
				event.preventDefault();
				event.stopPropagation();
				erpnext.entries.open_entry({
					entry_doctype: $(this).attr("data-entry-doctype"),
					name: $(this).attr("data-entry"),
					mode: "inspect",
				});
			});

		// the view switcher (PDF / List / XLSX) and the bottom summary bar
		// are shared with the Balance report (report_views.bundle.js): the
		// summary moves below the datatable in list view, the pdf / xlsx
		// placeholders mount with the current filter values, and a dock
		// context change re-runs the query and re-mounts the active view
		erpnext.reports.setup_views(report, {
			report_name: "Ledger Data",
			views: {
				pdf: {
					mount(el) {
						el.innerHTML = "";
						el.appendChild(
							frappe.ui.empty_state({
								icon: "file-text",
								title: __("Apercu PDF, bientot disponible"),
								description: __("The PDF preview will be generated from the XLSX view."),
							})
						);
					},
					unmount() {},
				},
				xlsx: {
					mount(el) {
						el.innerHTML = "";
						el.appendChild(
							frappe.ui.empty_state({
								icon: "table",
								title: __("XLSX view, coming soon"),
								description: __("The XLSX view will be generated from the same data."),
							})
						);
					},
					unmount() {},
				},
			},
		});
	}
};
