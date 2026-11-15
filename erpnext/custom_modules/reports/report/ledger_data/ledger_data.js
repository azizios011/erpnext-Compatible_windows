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

// the order the switcher shows
const LEDGER_VIEW_ORDER = ["pdf", "list", "xlsx"];

const LEDGER_VIEW_META = {
	pdf: { label: __("PDF View"), icon: "file-text", css_class: "ledger-view-pdf" },
	list: { label: __("List View"), icon: "list" },
	xlsx: { label: __("XLSX View"), icon: "table", css_class: "ledger-view-xlsx" },
};

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

		// ── the three views: list (native report) / pdf / xlsx ───────────────
		const view_state = {
			active: "list", // the default view on every load
			containers: {},
			switcher: null,
		};

		if (!frappe._ledger_view_css) {
			frappe._ledger_view_css = true;
			$(`<style>
				.layout-main-section.ledger-wide { padding: 0; }
				.ledger-view-pdf, .ledger-view-xlsx {
					width: 100%;
					height: calc(100vh - var(--navbar-height, 48px) - var(--page-head-height, 60px));
					background: var(--bg-color);
				}
				.report-summary.ledger-summary-bottom {
					position: sticky;
					bottom: 0;
					z-index: 5;
					margin: 0;
					border-radius: 0;
					border-bottom: none;
					border-top: 1px solid var(--border-color);
					background-color: var(--bg-color);
					width: 100%;
				}
			</style>`).appendTo("head");
		}

		// one wide-open container per non-list view, hidden unless active
		Object.entries(LEDGER_VIEW_META).forEach(([view, meta]) => {
			if (!meta.css_class) return;
			view_state.containers[view] = $(
				`<div class="${meta.css_class}" style="display: none;"></div>`
			).appendTo(report.page.main);
		});

		const set_trigger_content = () => {
			frappe.ui.button.dress(view_state.switcher.$trigger, {
				label: LEDGER_VIEW_META[view_state.active].label,
				icon: LEDGER_VIEW_META[view_state.active].icon,
				icon_right: "chevrons-up-down",
			});
			view_state.switcher.$trigger
				.find(".es-button__label")
				.addClass("hidden-xs custom-btn-group-label");
			view_state.switcher.$trigger.children("svg").last().addClass("hidden-xs");
		};

		const get_view_options = () =>
			LEDGER_VIEW_ORDER.map((view) => {
				const item = {
					label: LEDGER_VIEW_META[view].label,
					icon: LEDGER_VIEW_META[view].icon,
				};
				if (view_state.active === view) item.selected = true;
				else item.onclick = () => set_view(view);
				return item;
			});

		const make_switcher = () => {
			// same markup and behaviour as frappe.views.ListViewSelect: a
			// custom-btn-group view-switcher with a frappe.ui.Dropdown behind
			// its frappe.ui.button trigger
			const $wrapper = $('<div class="custom-btn-group view-switcher"></div>');
			const $trigger = frappe.ui.button({ css_class: "ellipsis" });
			set_trigger_content();
			$wrapper.append($trigger);
			view_state.switcher.$wrapper = $wrapper;
			view_state.switcher.$trigger = $trigger;
			view_state.switcher.dropdown = new frappe.ui.Dropdown({
				trigger: $trigger,
				options: () => get_view_options(),
			});
			const parent = frappe.is_mobile()
				? report.page.custom_mobile_actions
				: report.page.custom_actions;
			// a re-onload must never duplicate the switcher
			parent.removeClass("hide").find(".view-switcher").remove();
			parent.removeClass("hide").append($wrapper);
		};

		// Frappe renders the summary above the datatable: the List view wants
		// it at the bottom, sticky so it stays visible over long tables.
		// Frappe re-shows it after every refresh — the
		// after_datatable_render hook below re-applies this.
		const move_summary_below = () => {
			report.$summary.addClass("ledger-summary-bottom").appendTo(report.page.main);
			report.$summary.show();
		};

		const show_list = () => {
			// restore the native report: filters, datatable, summary at the
			// bottom — no re-query, the loaded data stays
			report.page.show_form();
			report.$report.show();
			report.page.main.removeClass("ledger-wide");
			Object.values(view_state.containers).forEach(($container) => $container.hide());
			move_summary_below();
		};

		const show_placeholder = (view) => {
			// hide the native report and mount the placeholder with the
			// CURRENT filter values
			report.page.hide_form();
			report.$report.hide();
			report.$summary.hide();
			report.page.main.addClass("ledger-wide");
			const container = view_state.containers[view];
			container.show();
			const mount = frappe.query_reports["Ledger Data"].views[view]?.mount;
			if (mount) mount(container[0], report.get_filter_values());
		};

		const set_view = (view) => {
			if (view_state.active === view) return;
			const previous = view_state.active;
			if (previous !== "list") {
				const unmount = frappe.query_reports["Ledger Data"].views[previous]?.unmount;
				if (unmount) unmount();
			}
			view_state.active = view;
			if (view === "list") show_list();
			else show_placeholder(view);
			set_trigger_content();
			if (view_state.switcher.dropdown.set_options) {
				view_state.switcher.dropdown.set_options(get_view_options());
			}
		};

		make_switcher();

		// Frappe re-shows the summary (and the datatable) on every refresh:
		// re-apply the bottom position in list view and re-hide the native
		// pieces when a placeholder view is active
		report.report_settings.after_datatable_render = () => {
			move_summary_below();
			if (view_state.active !== "list") {
				report.page.hide_form();
				report.$report.hide();
				report.$summary.hide();
				report.page.main.addClass("ledger-wide");
			}
		};

		// a dock context change re-runs the list query and re-mounts the
		// active placeholder view with the fresh filters
		$(document)
			.off("axeane-context-changed.ledger-data")
			.on("axeane-context-changed.ledger-data", () => {
				set_title();
				frappe.query_report.refresh();
				if (view_state.active !== "list") {
					show_placeholder(view_state.active);
				} else {
					move_summary_below();
				}
			});
	}
};
