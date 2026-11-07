// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// "Ledger Data" (Grand Livre): the standard filter+table view, plus the
// Axeane "Rapport PDF" viewer (HTML paper rendered server-side per page).
// The PDF view reuses the filters already chosen in the list view.

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
			options: GL_MONTHS.join("\n"),
			default: GL_MONTHS[frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth()],
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
		let pdf_visible = false;
		const set_filters_visible = (visible) => {
			filters_visible = visible;
			$(report.page.page_form).toggle(visible);
			btn_hide_filters.toggleClass("hidden", !visible);
			btn_show_filters.toggleClass("hidden", visible);
		};
		const set_pdf_visible = (visible) => {
			pdf_visible = visible;
			if (visible) {
				gl_pdf_view.show(report);
				if (filters_visible) set_filters_visible(false);
			} else {
				gl_pdf_view.hide(report);
				if (!filters_visible) set_filters_visible(true);
			}
			btn_pdf.toggleClass("hidden", visible);
			btn_list.toggleClass("hidden", !visible);
		};
		const btn_hide_filters = report.page.add_inner_button(__("Cacher filtres"), () =>
			set_filters_visible(false)
		);
		const btn_show_filters = report.page.add_inner_button(__("Afficher filtres"), () =>
			set_filters_visible(true)
		);
		const btn_pdf = report.page.add_inner_button(__("Vue PDF"), () => set_pdf_visible(true));
		const btn_list = report.page.add_inner_button(__("Vue Liste"), () => set_pdf_visible(false));
		btn_show_filters.addClass("hidden");
		btn_list.addClass("hidden");

	},
};

const gl_pdf_view = {
	zoom: 1,
	state: null,

	show(report) {
		this.state = {
			report,
			filters: JSON.stringify(report.get_values()),
			layout: "Simple",
			page: 1,
			total_pages: 1,
			zoom: 1,
		};
		report.$report.hide();
		report.$summary && report.$summary.hide();
		if (!this.$container) {
			this.make(report);
		}
		this.$container.show();
		this.fetch();
	},

	hide(report) {
		if (this.$container) this.$container.hide();
		report.$report.show();
		report.$summary && report.$summary.show();
	},

	make(report) {
		this.$container = $(
			`<div class="gl-pdf-view">
				<div class="gl-pdf-toolbar" style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">
					<label>${__("Layout")}</label>
					<select class="form-control gl-layout" style="width:140px;">
						<option value="Simple">${__("Simple")}</option>
						<option value="Detaille">${__("Detaille")}</option>
					</select>
					<button class="btn btn-primary btn-sm gl-show">${__("Afficher")}</button>
					<button class="btn btn-default btn-sm gl-print">${__("Imprimer")}</button>
					<span class="text-muted gl-pager-info"></span>
					<button class="btn btn-default btn-sm gl-prev">&larr;</button>
					<button class="btn btn-default btn-sm gl-next">&rarr;</button>
					<button class="btn btn-default btn-sm gl-zoom-out">-</button>
					<button class="btn btn-default btn-sm gl-zoom-in">+</button>
				</div>
				<div class="gl-pdf-viewer" style="background: #3a3a3a; padding: 16px; overflow: auto; border-radius: 6px; max-height: calc(100vh - 220px);">
					<div class="gl-pdf-page" style="background: #fff; width: 21cm; min-height: 29.7cm; margin: 0 auto; padding: 12mm; box-shadow: 0 2px 8px rgba(0,0,0,.5); transform-origin: top center;"></div>
				</div>
			</div>`
		);
		report.page.main.append(this.$container);

		this.$container.find(".gl-show").on("click", () => {
			this.state.page = 1;
			this.state.layout = this.$container.find(".gl-layout").val();
			this.fetch();
		});
		this.$container.find(".gl-prev").on("click", () => {
			if (this.state.page > 1) {
				this.state.page -= 1;
				this.fetch();
			}
		});
		this.$container.find(".gl-next").on("click", () => {
			if (this.state.page < this.state.total_pages) {
				this.state.page += 1;
				this.fetch();
			}
		});
		this.$container.find(".gl-zoom-in").on("click", () => this.apply_zoom(this.state.zoom + 0.1));
		this.$container.find(".gl-zoom-out").on("click", () => this.apply_zoom(this.state.zoom - 0.1));
		this.$container.find(".gl-print").on("click", () => {
			frappe.call({
				method: "erpnext.custom_modules.reports.report.ledger_data.ledger_data.get_pdf_view_all",
				args: { filters: this.state.filters, layout: this.state.layout },
				callback(r) {
					const message = r.message || {};
					const win = window.open("", "_blank");
					if (!win) {
						frappe.msgprint(__("Allow pop-ups to print."));
						return;
					}
					win.document.write(
						`<!doctype html><html><head><title>${__("Grand Livre")}</title></head><body>${message.html}</body></html>`
					);
					win.document.close();
					win.focus();
					win.print();
				},
			});
		});
	},

	apply_zoom(zoom) {
		this.state.zoom = Math.min(2, Math.max(0.5, zoom));
		this.$container.find(".gl-pdf-page").css("transform", `scale(${this.state.zoom})`);
	},

	fetch() {
		const { filters, layout, page } = this.state;
		frappe.call({
			method: "erpnext.custom_modules.reports.report.ledger_data.ledger_data.get_pdf_view",
			args: { filters, layout, page },
			freeze: true,
			callback: (r) => {
				const message = r.message || {};
				this.state.total_pages = message.total_pages || 1;
				this.$container.find(".gl-pdf-page").html(message.html || "");
				this.$container
					.find(".gl-pager-info")
					.text(__("Page {0} of {1}", [message.page, message.total_pages]));
			},
		});
	},
};
