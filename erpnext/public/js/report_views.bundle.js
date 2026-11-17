// Shared report view plumbing for the Reports-module script reports
// (Ledger Data, Balance): the PDF / List / XLSX view switcher and the bottom
// summary bar. Built like frappe.views.ListViewSelect (custom-btn-group
// view-switcher, frappe.ui.button trigger dressed with label + icon +
// chevrons-up-down, frappe.ui.Dropdown options with selected / onclick).
// erpnext.reports.setup_views(report, { report_name, views }) — opts.views
// carries the per-view mount / unmount hooks; the summary is moved below the
// datatable in list view, re-applied after every refresh, and hidden while a
// placeholder view is active.
(function () {
	"use strict";

	frappe.provide("erpnext.reports");

	const VIEW_ORDER = ["pdf", "list", "xlsx"];

	const VIEW_META = {
		pdf: { label: __("PDF View"), icon: "file-text", css_class: "report-view-pdf" },
		list: { label: __("List View"), icon: "list" },
		xlsx: { label: __("XLSX View"), icon: "table", css_class: "report-view-xlsx" },
	};

	erpnext.reports.setup_views = function (report, opts) {
		opts = opts || {};
		const views = opts.views || {};

		const view_state = {
			active: "list", // the default view on every load
			containers: {},
			// the $wrapper / $trigger / dropdown elements land here in
			// make_switcher, which stores them BEFORE set_trigger_content
			// reads them — a null here would throw on the first property set
			switcher: {},
		};

		if (!frappe._report_views_css) {
			frappe._report_views_css = true;
			$(`<style>
				.layout-main-section.report-wide { padding: 0; }
				.report-view-pdf, .report-view-xlsx {
					width: 100%;
					height: calc(100vh - var(--navbar-height, 48px) - var(--page-head-height, 60px));
					background: var(--bg-color);
				}
				.report-summary.report-summary-bottom {
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
				/* opt-in bottom bar (opts.pagination): the sticky area under the
				   datatable carries the summary cards AND the pagination */
				.report-bottom-bar {
					display: flex;
					align-items: center;
					gap: 16px;
					padding: 6px 15px;
					border-top: 1px solid var(--border-color);
					background-color: var(--bg-color);
					width: 100%;
				}
				.report-bottom-bar .report-summary {
					flex: 1 1 auto;
					margin: 0;
					padding: 0;
					justify-content: flex-start;
					border: none;
				}
				.report-bottom-bar .report-summary .summary-item {
					padding: 4px 12px;
				}
				.report-pagination {
					display: flex;
					align-items: center;
					gap: 12px;
					flex: none;
				}
				.report-pagination .gl-showing {
					font-size: 12px;
					white-space: nowrap;
				}
				/* opt-in full-height list (the report page sets report-gl-fill):
				   the section becomes a flex column — filters, datatable, bottom
				   bar — and the datatable body takes the height that is left */
				.layout-main-section.report-gl-fill {
					height: calc(100vh - var(--navbar-height, 48px) - var(--page-head-height, 60px));
					display: flex;
					flex-direction: column;
					overflow: hidden;
				}
				.report-gl-fill .page-form {
					flex-shrink: 0;
					padding-top: 10px;
					padding-bottom: 6px;
				}
				.report-gl-fill .report-wrapper {
					flex: 1 1 auto;
					min-height: 0;
					overflow: hidden;
					display: flex;
					flex-direction: column;
				}
				.report-gl-fill .report-wrapper .datatable {
					flex: 1 1 auto;
					min-height: 0;
					display: flex;
					flex-direction: column;
				}
				.report-gl-fill .report-wrapper .dt-header {
					flex-shrink: 0;
				}
				.report-gl-fill .report-wrapper .dt-scrollable {
					height: auto;
					flex: 1 1 auto;
					overflow: auto;
				}
			</style>`).appendTo("head");
		}

		// opt-in pagination (opts.pagination): the report owns the state and
		// the render($area) callback; the bundle only provides the bottom bar
		// container next to the summary cards. Absent for Balance: no change.
		const pagination = opts.pagination || null;
		let $bottom_bar = null;
		let $pagination_area = null;
		if (pagination) {
			$bottom_bar = $(`<div class="report-bottom-bar"></div>`);
			$pagination_area = $(`<div class="report-pagination"></div>`).appendTo($bottom_bar);
			$bottom_bar.appendTo(report.page.main);
		}

		// one wide-open container per non-list view, hidden unless active
		// (created once per report page: onload can run again on every visit)
		Object.entries(VIEW_META).forEach(([view, meta]) => {
			if (!meta.css_class) return;
			let $container = report.page.main.find("." + meta.css_class);
			if (!$container.length) {
				$container = $(`<div class="${meta.css_class}" style="display: none;"></div>`).appendTo(
					report.page.main
				);
			}
			view_state.containers[view] = $container;
		});

		const set_trigger_content = () => {
			frappe.ui.button.dress(view_state.switcher.$trigger, {
				label: VIEW_META[view_state.active].label,
				icon: VIEW_META[view_state.active].icon,
				icon_right: "chevrons-up-down",
			});
			view_state.switcher.$trigger
				.find(".es-button__label")
				.addClass("hidden-xs custom-btn-group-label");
			view_state.switcher.$trigger.children("svg").last().addClass("hidden-xs");
		};

		const get_view_options = () =>
			VIEW_ORDER.map((view) => {
				const item = { label: VIEW_META[view].label, icon: VIEW_META[view].icon };
				if (view_state.active === view) item.selected = true;
				else item.onclick = () => set_view(view);
				return item;
			});

		const make_switcher = () => {
			// the elements are stored on view_state.switcher BEFORE
			// set_trigger_content() reads them
			const $wrapper = $('<div class="custom-btn-group view-switcher"></div>');
			const $trigger = frappe.ui.button({ css_class: "ellipsis" });
			view_state.switcher.$wrapper = $wrapper;
			view_state.switcher.$trigger = $trigger;
			set_trigger_content();
			$wrapper.append($trigger);
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
		// after_datatable_render hook below re-applies this. With the opt-in
		// pagination the summary joins the bottom bar and the pagination
		// controls re-render next to it.
		const move_summary_below = () => {
			if ($bottom_bar) {
				report.$summary.addClass("report-summary-bottom").prependTo($bottom_bar);
				report.$summary.show();
				$bottom_bar.show();
				if (pagination.render) pagination.render($pagination_area);
			} else {
				report.$summary.addClass("report-summary-bottom").appendTo(report.page.main);
				report.$summary.show();
			}
		};

		const show_list = () => {
			// restore the native report: filters, datatable, summary at the
			// bottom — no re-query, the loaded data stays
			report.page.show_form();
			report.$report.show();
			report.page.main.removeClass("report-wide");
			Object.values(view_state.containers).forEach(($container) => $container.hide());
			move_summary_below();
		};

		const show_placeholder = (view) => {
			// hide the native report and mount the placeholder with the
			// CURRENT filter values
			if (!opts.keep_filters) {
				report.page.hide_form();
			} else {
				report.page.show_form();
			}
			report.$report.hide();
			report.$summary.hide();
			if ($bottom_bar) $bottom_bar.hide();
			report.page.main.addClass("report-wide");
			const container = view_state.containers[view];
			container.show();
			const mount = views[view] && views[view].mount;
			if (mount) mount(container[0], report.get_filter_values());
		};

		const set_view = (view) => {
			if (view_state.active === view) return;
			const previous = view_state.active;
			if (previous !== "list") {
				const unmount = views[previous] && views[previous].unmount;
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
				if (!opts.keep_filters) report.page.hide_form();
				report.$report.hide();
				report.$summary.hide();
				report.page.main.addClass("report-wide");
			}
		};

		// a dock context change re-runs the list query and re-mounts the
		// active placeholder view with the fresh filters
		$(document)
			.off("axeane-context-changed.report-views-" + (opts.report_name || "default"))
			.on("axeane-context-changed.report-views-" + (opts.report_name || "default"), () => {
				frappe.query_report.refresh();
				if (view_state.active !== "list") {
					if (!opts.keep_filters) report.page.hide_form();
					report.$report.hide();
					report.$summary.hide();
					if ($bottom_bar) $bottom_bar.hide();
					report.page.main.addClass("report-wide");
					const mount = views[view_state.active] && views[view_state.active].mount;
					if (mount) mount(view_state.containers[view_state.active][0], report.get_filter_values());
				} else {
					move_summary_below();
				}
			});
};
})();
