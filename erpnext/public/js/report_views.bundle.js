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
				   datatable carries the pagination; with opts.summary_position
				   "top" the summary cards live in their own bar instead */
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
				/* opt-in top summary (opts.summary_position = "top"): the cards
				   sit directly under the filter bar, above the table, persistent
				   across refreshes (values updated in place, dimmed while the
				   query runs) and sticky under the header if the page scrolls */
				.report-summary-top {
					position: sticky;
					top: 0;
					z-index: 5;
					flex-shrink: 0;
					border-bottom: 1px solid var(--border-color);
					background-color: var(--bg-color);
					width: 100%;
					transition: opacity 0.2s ease;
				}
				.report-summary-top.gl-summary-loading {
					opacity: 0.45;
				}
				.report-summary-top .report-summary {
					margin: 0;
					padding: 6px 15px;
					justify-content: flex-start;
					gap: 4px;
				}
				.report-summary-top .report-summary .summary-item {
					padding: 4px 14px;
					border-right: 1px solid var(--border-color);
				}
				.report-summary-top .report-summary .summary-item:last-child {
					border-right: none;
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
					/* the virtual scroller reads clientHeight at every render and
					   is sticky about it: a degenerate (0) measure renders zero
					   rows forever — the floor guarantees a renderable window no
					   matter the flex/layout timing; the exact pixel height is
					   re-asserted from JS after every render (see fit_datatable) */
					min-height: 240px;
					flex: 1 1 auto;
					overflow: auto;
				}
				/* row action icons (Ledger Data list only): a small
				   round-cornered icon button group, centered in the narrow
				   last column — enabled icons carry the accent color, the
				   greyed ones are not clickable */
				.gl-row-actions {
					display: inline-flex;
					width: 100%;
					align-items: center;
					justify-content: center;
					gap: 4px;
				}
				.gl-row-actions .gl-row-action {
					width: 26px;
					height: 26px;
					padding: 0;
					display: inline-flex;
					align-items: center;
					justify-content: center;
					border-radius: 6px;
					color: var(--primary);
					background: transparent;
					border: 1px solid var(--border-color, #d1d8dd);
				}
				.gl-row-actions .gl-row-action:hover:not(.gl-action-disabled) {
					background: var(--control-bg, #f3f3f3);
					color: var(--primary);
				}
				.gl-row-actions .gl-row-action.gl-action-disabled {
					color: var(--text-muted, #8d99ae);
					opacity: 0.45;
					cursor: not-allowed;
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

		// opt-in top summary (opts.summary_position = "top"): the cards sit
		// directly under the filter bar, ABOVE the table, in a bar built once
		// and persistent — frappe empties + rebuilds report.$summary on every
		// refresh, so render_summary is patched to update the card values IN
		// PLACE (same synchronous tick as the wipe: no visible flash, no
		// layout jump) and the bar is dimmed while a query runs. The numbers
		// stay global over all filtered rows (they come from the server's
		// report_summary, computed over the whole filtered set).
		const summary_on_top = opts.summary_position === "top";
		let $summary_bar = null;
		if (summary_on_top) {
			$summary_bar = $(`<div class="report-summary-top"></div>`);
			if (report.page.page_form && report.page.page_form.length) {
				report.page.page_form.after($summary_bar);
			} else {
				$summary_bar.prependTo(report.page.main);
			}
			report.$summary.addClass("report-summary-in-top-bar").appendTo($summary_bar);
			report.$summary.removeClass("report-summary-bottom");

			const render_summary_original = report.render_summary;
			report.render_summary = function (data) {
				if (!Array.isArray(data)) {
					return render_summary_original.call(this, data);
				}
				const existing = {};
				this.$summary.find(".summary-item").each(function () {
					existing[$(this).find(".summary-label").text().trim()] = $(this);
				});
				const seen = new Set();
				data.forEach((item) => {
					seen.add(__(item.label));
					const $card = existing[__(item.label)];
					if (!$card) {
						this.$summary.append(frappe.utils.build_summary_item(item));
						return;
					}
					// update the value + indicator in place, no rebuild flash
					const df = { fieldtype: item.datatype };
					let doc = null;
					if (item.datatype === "Currency") {
						df.options = "currency";
						doc = { currency: item.currency };
					}
					const value = frappe.format(item.value, df, { only_value: true }, doc);
					const color = item.indicator ? String(item.indicator).toLowerCase() : "";
					const $value = $card.find(".summary-value");
					$value.removeClass().addClass(`summary-value ${color}`).html(value);
				});
				// cards the server no longer sends go away (e.g. empty run)
				this.$summary.find(".summary-item").each(function () {
					if (!seen.has($(this).find(".summary-label").text().trim())) {
						$(this).remove();
					}
				});
				this.$summary.show();
				if ($summary_bar) $summary_bar.removeClass("gl-summary-loading");
			};

			// dim the cards while a query runs (last values stay visible),
			// undimmed by render_summary above or by after_refresh on errors
			const refresh_original = report.refresh;
			report.refresh = function () {
				if ($summary_bar) $summary_bar.addClass("gl-summary-loading");
				return refresh_original.apply(this, arguments);
			};
			const previous_after_refresh = report.report_settings.after_refresh;
			report.report_settings.after_refresh = () => {
				$summary_bar.removeClass("gl-summary-loading");
				if (previous_after_refresh) previous_after_refresh();
			};
		}

		// opt-in full-height list (opts.fill_datatable, set with the
		// report-gl-fill class): the datatable body is a virtual scroller
		// whose visible window is computed from clientHeight AT RENDER TIME
		// and cached (HyperList repaints only on scroll changes) — a render
		// that happens while the container has no height yet renders ZERO
		// rows and never heals by itself. So: the CSS floor (min-height)
		// keeps every render renderable, and this fit helper re-asserts the
		// exact pixel height + re-renders the body after every render, view
		// switch, page change and window resize.
		let fit_datatable = null;
		if (opts.fill_datatable) {
			const throttled_fit = (() => {
				let timer = null;
				return () => {
					if (timer) return;
					timer = setTimeout(() => {
						timer = null;
						fit_datatable_body();
					}, 150);
				};
			})();
			function fit_datatable_body() {
				if (view_state.active !== "list") return;
				const datatable = report.datatable;
				if (!datatable || !datatable.bodyScrollable || !report.$report || !report.$report.length) return;
				const wrapper = report.$report[0];
				if (!wrapper.offsetParent) return; // hidden: nothing to measure
				const body = datatable.bodyScrollable;
				const header = datatable.header;
				const bar = $bottom_bar && $bottom_bar.is(":visible") ? $bottom_bar.outerHeight(true) : 0;
				const available = Math.max(window.innerHeight - wrapper.getBoundingClientRect().top - bar - 8, 180);
				const header_height = header ? header.getBoundingClientRect().height : 0;
				const height = Math.max(Math.floor(available - header_height), 180);
				const previous = parseFloat(body.style.height) || 0;
				body.style.height = height + "px";
				// (re)render the body against the fresh container size — heals
				// any stale or degenerate virtual-render window
				if (Math.abs(previous - height) > 1 || previous === 0) {
					if (datatable.rowmanager && datatable.rowmanager.showAllRows) {
						try {
							datatable.rowmanager.showAllRows();
						} catch (error) {
							console.error("report_views: body re-render failed", error);
						}
					}
				}
			}
			fit_datatable = fit_datatable_body;
			$(window)
				.off("resize.report-views-fill")
				.on("resize.report-views-fill", throttled_fit);
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
		// it either directly under the filters (opts.summary_position = "top",
		// persistent bar) or at the bottom next to the pagination. Frappe
		// re-shows it after every refresh — the after_datatable_render hook
		// below re-applies the placement.
		const move_summary_below = () => {
			if (summary_on_top) {
				// the cards bar stays under the filters; re-place defensively
				// (frappe never moves report.$summary, but re-onload could)
				if (!$.contains(report.page.main[0], $summary_bar[0])) {
					if (report.page.page_form && report.page.page_form.length) {
						report.page.page_form.after($summary_bar);
					} else {
						$summary_bar.prependTo(report.page.main);
					}
				}
				$summary_bar.show();
				report.$summary.show();
				if ($bottom_bar) {
					$bottom_bar.show();
					if (pagination.render) pagination.render($pagination_area);
				}
				return;
			}
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
			if (fit_datatable) fit_datatable(); // the wrapper just became visible
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
			if ($summary_bar) $summary_bar.hide();
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
		// re-apply the bottom position in list view, re-assert the datatable
		// body height, and re-hide the native pieces when a placeholder view
		// is active
		report.report_settings.after_datatable_render = () => {
			move_summary_below();
			if (view_state.active !== "list") {
				if (!opts.keep_filters) report.page.hide_form();
				report.$report.hide();
				report.$summary.hide();
				report.page.main.addClass("report-wide");
			} else if (fit_datatable) {
				// setDimensions just stripped the body's inline height: re-fit
				// AFTER every render so the virtual scroller's window matches
				// the real layout (its measure is sticky)
				fit_datatable();
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
					if (fit_datatable) fit_datatable();
				}
			});
};
})();
