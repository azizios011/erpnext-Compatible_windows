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

	// ── the shared bundled Sheets editor (print_designer/editors/sheets) ────
	// One iframe + postMessage handshake for every report that embeds a
	// workbook read-only (Ledger Data's xlsx view, the Declaration Mensuelle
	// Vue XLSX). Returns the cleanup that removes the message listener — the
	// host owns when the editor goes away. Same handshake as the desk's
	// /app/sheets-editor page.
	erpnext.reports.mount_sheets_editor = function (area, file_docname, opts = {}) {
		const iframe = document.createElement("iframe");
		iframe.title = opts.title || __("Sheets");
		iframe.style.cssText = "border: 0; width: 100%; height: 100%; display: block;";
		area.appendChild(iframe);
		const on_message = (ev) => {
			if (ev.source !== iframe.contentWindow) return;
			const data = ev.data || {};
			if (data.type !== "sheets-editor-ready") return;
			iframe.contentWindow.postMessage(
				{
					type: "sheets-editor-init",
					file: file_docname,
					lang: frappe.boot.lang || "en",
					csrfToken: frappe.csrf_token,
					fullName: frappe.user_info(frappe.session.user).fullname,
					readonly: opts.readonly !== false,
					// grid only: no ribbon, no formula bar, no sheet tabs, no save
					mode: opts.mode || "preview",
				},
				window.location.origin
			);
		};
		window.addEventListener("message", on_message);
		iframe.src = "/assets/print_designer/editors/sheets/index.html";
		return () => window.removeEventListener("message", on_message);
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
				/* inside the full-height list layout (report-gl-fill): the
				   document view starts right under the page header (where the
				   view picker is) and fills to the bottom of the viewport —
				   flex, no fixed calc; the native bands above it are hidden
				   while a document view is active (see after_refresh) */
				.layout-main-section.report-gl-fill .report-view-pdf,
				.layout-main-section.report-gl-fill .report-view-xlsx {
					height: auto;
					flex: 1 1 auto;
					min-height: 0;
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
					/* the list view's cards sit centered (the bottom bar keeps
					   its own left-aligned layout) */
					justify-content: center;
					gap: 4px;
				}
				.report-summary-top .report-summary .summary-item {
					padding: 4px 14px;
					border-right: 1px solid var(--border-color);
					align-items: center;
					text-align: center;
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
				/* the Filtres toggle: in the document views the whole filter
				   section is hidden (the document fills the screen); the toggle
				   slides it down as an overlay panel above everything */
				.report-gl-fill.gl-filters-open .page-form.hide {
					display: flex !important;
					position: absolute;
					top: 0;
					left: 0;
					right: 0;
					z-index: 40;
					background-color: var(--bg-color);
					border-bottom: 1px solid var(--border-color);
					box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.08));
					max-height: 60vh;
					overflow: auto;
					padding: 10px 15px 8px;
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
				/* single header row for Ledger Data: neutralize the plain title
				   row and style the filter row as the only visible header.
				   NEVER display:none on .dt-row-header: the datatable measures
				   every column width from this row — setupNaturalColumnWidth
				   reads its .dt-cell__content widths and distributeRemainingWidth
				   reads its cells via getColumnHeaderElement — so a hidden row
				   measures 0 / NaN and every column collapses to content width.
				   Keep it laid out and measurable but invisible and
				   non-interactive (visibility and pointer-events change no
				   layout); the filter row stays the only visible header row.
				   The stylesheet is static and precedes the datatable, so every
				   setDimensions already measures correctly — no re-measure hook
				   is needed for this styling. */
				.layout-main-section.report-gl-fill .dt-header .dt-row-header {
					height: 0 !important;
					min-height: 0 !important;
					overflow: hidden;
					visibility: hidden;
					pointer-events: none;
					border: 0;
					padding: 0;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-header .dt-cell__content {
					height: 0 !important;
					min-height: 0 !important;
					overflow: hidden;
					visibility: hidden;
					pointer-events: none;
					border: 0;
					padding: 0;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter {
					display: flex !important;
					height: 36px;
					background-color: var(--subtle-fg, #f8f9fa);
					border-bottom: 1px solid var(--border-color, #d1d8dd);
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .dt-cell {
					background-color: var(--subtle-fg, #f8f9fa);
					position: relative;
					overflow: visible;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .dt-cell__content {
					display: flex;
					align-items: center;
					padding: 3px 6px;
					height: 100%;
					position: relative;
					overflow: visible;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .dt-filter.dt-input {
					flex: 1 1 auto;
					min-width: 0;
					height: 26px;
					font-size: 11px;
					font-weight: 500;
					border: 1px solid var(--border-color, #d1d8dd);
					border-radius: 4px;
					padding: 0 6px;
					background-color: var(--control-bg, #fff);
					color: var(--text-color, #1f272e);
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .dt-filter.dt-input::placeholder {
					color: var(--text-muted, #8d99ae);
					font-size: 11px;
					font-weight: 500;
					text-overflow: ellipsis;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .dt-filter.dt-input:focus {
					border-color: var(--primary, #171717);
					box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.05);
					outline: none;
					background-color: #fff;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .gl-col-sort {
					flex: 0 0 auto;
					display: inline-flex;
					align-items: center;
					justify-content: center;
					width: 18px;
					height: 24px;
					margin-left: 2px;
					cursor: pointer;
					color: var(--text-muted, #8d99ae);
					border-radius: 3px;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .gl-col-sort:hover {
					color: var(--text-color, #1f272e);
					background-color: rgba(0, 0, 0, 0.05);
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .gl-col-sort .gl-sort-icon.active {
					color: var(--primary, #171717);
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .dt-cell__resize-handle {
					position: absolute;
					right: -2px;
					top: 0;
					width: 5px;
					height: 100%;
					cursor: col-resize;
					z-index: 10;
					opacity: 0;
				}
				.layout-main-section.report-gl-fill .dt-header .dt-row-filter .dt-cell:hover .dt-cell__resize-handle {
					opacity: 1;
					background-color: var(--primary, #5292f7);
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
			show_report_chrome();
			report.$report.show();
			report.page.main.removeClass("report-wide");
			Object.values(view_state.containers).forEach(($container) => $container.hide());
			move_summary_below();
			// one re-measure, now that the report area is visible again: the
			// datatable's own window-resize handler keeps running while a
			// document view has $report hidden and reads the wrapper's width
			// as 'auto' (display:none) — the fluid width distribution then
			// stores NaN widths that would collapse the grid on return.
			// setDimensions re-reads every width from the laid-out wrapper and
			// fires no events, so it cannot loop; show_list runs only on an
			// actual document → list switch, so this runs once per switch.
			if (report.datatable && typeof report.datatable.setDimensions === "function") {
				try {
					report.datatable.setDimensions();
				} catch (error) {
					console.error("report_views: datatable re-measure failed", error);
				}
			}
			if (fit_datatable) fit_datatable(); // the wrapper just became visible
			// the list Filtres toggle returns with the list (the document
			// views keep their own overlay toggle) and the remembered inline
			// state re-applies — show_report_chrome just re-showed the filters
			$filters_toggle.show();
			set_filters_visible(filters_visible, false);
		};

		// opts.hide_filters_in_doc (the Ledger Data document views): the
		// filter section, summary cards, pagination bar and the report hint /
		// execution-time footer all hide, so the document fills the screen
		// under the page header; the host provides a Filtres toggle that
		// slides the filter panel down as an overlay (gl-filters-open)
		const hide_filters_in_doc = !!opts.hide_filters_in_doc;
		const hide_report_chrome = () => {
			if (hide_filters_in_doc) report.page.hide_form();
			else if (!opts.keep_filters) report.page.hide_form();
			if (report.$report_footer) report.$report_footer.hide();
		};
		const show_report_chrome = () => {
			report.page.main.removeClass("gl-filters-open"); // a left-open overlay never leaks
			report.page.show_form();
			if (report.$report_footer) report.$report_footer.show();
		};

		const show_placeholder = (view) => {
			// hide the native report and mount the placeholder with the
			// CURRENT filter values
			$filters_toggle.hide(); // the document views keep their own overlay toggle
			if (hide_filters_in_doc) {
				hide_report_chrome();
			} else if (!opts.keep_filters) {
				report.page.hide_form();
			} else {
				report.page.show_form();
			}
			report.$report.hide();
			report.$summary.hide();
			if ($summary_bar) $summary_bar.hide();
			if ($bottom_bar) $bottom_bar.hide();
			// the native bands never show above a document view: the empty
			// state, the prepared-report / stale status band, the server
			// message, the loading band and the hint footer. after_refresh
			// re-hides them after every refresh while a view is active.
			[report.$message, report.$status, report.$report_message, report.$loading].forEach(
				($el) => $el && $el.hide && $el.hide()
			);
			if (report.$report_footer) report.$report_footer.hide();
			report.page.main.addClass("report-wide");
			// hide every OTHER view container before showing the target —
			// fixes the split-screen bug when switching xlsx→pdf or pdf→xlsx
			Object.entries(view_state.containers).forEach(([k, $c]) => {
				if (k !== view) $c.hide();
			});
			const container = view_state.containers[view];
			container.show();
			const mount = views[view] && views[view].mount;
			if (mount) mount(container[0], report.get_filter_values());
			$(window).trigger("resize");
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

		// ── the LIST view's Filtres toggle ───────────────────────────────────
		// same place and style as the document views' overlay toggle (before
		// the view switcher), but INLINE: the filter section shows / hides and
		// the summary cards + datatable stay — the datatable grows into the
		// freed height (fit runs after every toggle). Default = shown; the
		// state is remembered per report in localStorage (private-mode safe:
		// on failure the default stands and nothing is stored). The document
		// views keep their own overlay toggle: this button hides while a
		// placeholder view is active.
		const filters_storage_key = "report_views.filters_visible." + (opts.report_name || "default");
		let filters_visible = true;
		try {
			const stored = localStorage.getItem(filters_storage_key);
			if (stored !== null) filters_visible = stored === "1";
		} catch (error) {
			// localStorage unavailable (private mode): the default stands
		}
		const $filters_toggle = $(
			`<button type="button" class="btn btn-default btn-sm gl-list-filters-toggle">${__("Filtres")}</button>`
		);
		const set_filters_visible = (visible, persist) => {
			filters_visible = visible;
			if (persist) {
				try {
					localStorage.setItem(filters_storage_key, visible ? "1" : "0");
				} catch (error) {
					// private mode: the state just is not remembered
				}
			}
			$filters_toggle.toggleClass("btn-primary", visible);
			if (visible) report.page.show_form();
			else report.page.hide_form();
			if (fit_datatable) fit_datatable(); // the datatable takes the freed height
		};
		const $switcher_parent = frappe.is_mobile()
			? report.page.custom_mobile_actions
			: report.page.custom_actions;
		// a re-onload must never duplicate the toggle (same guard as the
		// switcher above)
		$switcher_parent.removeClass("hide").find(".gl-list-filters-toggle").remove();
		$switcher_parent.append($filters_toggle);
		$switcher_parent.find(".view-switcher").before($filters_toggle);
		$filters_toggle.on("click", () => set_filters_visible(!filters_visible, true));
		set_filters_visible(filters_visible, false); // the remembered state applies on load

		// frappe's refresh flow re-shows its native pieces even while a
		// document view is on screen ($report on render, the empty state,
		// the prepared-report status band, the footer it re-creates): re-hide
		// them after EVERY refresh while a view is active — show_list (the
		// chrome restore) brings them back on the way to the list
		const previous_after_refresh = report.report_settings.after_refresh;
		report.report_settings.after_refresh = () => {
			if (previous_after_refresh) previous_after_refresh();
			if (view_state.active !== "list") {
				[report.$report, report.$message, report.$status, report.$report_message, report.$loading].forEach(
					($el) => $el && $el.hide && $el.hide()
				);
				if (report.$report_footer) report.$report_footer.hide();
			}
		};

		// Frappe re-shows the summary (and the datatable) on every refresh:
		// re-apply the bottom position in list view, re-assert the datatable
		// body height, and re-hide the native pieces when a placeholder view
		// is active
		report.report_settings.after_datatable_render = () => {
			move_summary_below();
			if (view_state.active !== "list") {
				hide_report_chrome();
				if (!hide_filters_in_doc && opts.keep_filters) report.page.show_form();
				report.$report.hide();
				report.$summary.hide();
				if (report.$report_footer) report.$report_footer.hide();
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
					hide_report_chrome();
					if (!hide_filters_in_doc && opts.keep_filters) report.page.show_form();
					report.$report.hide();
					report.$summary.hide();
					if ($bottom_bar) $bottom_bar.hide();
					if (report.$report_footer) report.$report_footer.hide();
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
