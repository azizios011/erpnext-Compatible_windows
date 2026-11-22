// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// "Lettrage" — the "Saisie du lettrage" tool as a Script Report. The old
// lettrage Page + Single doctype shared the /app/lettrage slug and frappe's
// router resolved the doctype first, opening an empty form: both are gone,
// the tool now lives on the native report page (like Ledger Data).
//
// Left: the account panel is injected beside the datatable (category tabs,
// search, hide-settled, sort, overview, account cards; clicking a card sets
// the hidden account filter and refreshes the report). Right: account head
// + status tabs above the datatable, the page-size / pagination bottom bar
// under it, and the sticky selection bar at the very bottom. The header
// buttons (auto lettrage / delettrage, Suggerer, Filtres, Affichage,
// Refresh) live on the report page header. Every query is scoped
// server-side by the dock context; a context switch re-runs the report and
// the panel, and the background auto passes report through the
// "lettrage_progress" realtime event.
//
// Filter split: the panel / tab state (account, tab, category, search,
// hide_settled) lives in HIDDEN filters driven by the panel UI, the
// user-facing line filters (from_date, to_date, journal, amount_min,
// amount_max, libelle) are the visible filter bar (the old Filtres dialog),
// and page / page_size are the hidden pagination filters (Ledger Data
// pattern — the "Showing X - Y of N rows (page P of M)." server message is
// intercepted to feed the bottom bar).
//
// frappe.query_report is a SINGLETON whose page is shared by every query
// report: the layout wraps the datatable only while Lettrage is on screen
// (lettrage_unwrap hands the datatable back before another report renders
// into it), and every instance-level wrapper (render_datatable,
// show_report_message, toggle_nothing_to_show, after_datatable_render)
// checks the active route — without the guard they would leak into Ledger
// Data / Balance and hide their columns.

const LETTRAGE_API = "erpnext.custom_modules.reports.lettrage_api.";
const LETTRAGE_CATEGORIES = ["Tous", "Clients", "Fournisseurs", "Salaries", "Debiteurs-Crediteurs", "Autres"];
const LETTRAGE_TABS = ["Non lettrees", "Partielles", "Lettrees", "Toutes"];
const LETTRAGE_PAGE_SIZES = [15, 25, 50, 100, 250];
const LETTRAGE_PAGE_SIZE = 25;
const LETTRAGE_TOLERANCE = 0.001;

// live state — rebuilt on every onload (route re-entry), null before
let LETTRAGE = null;

function lettrage_is_active() {
	// the singleton report instance serves every report: only run the
	// lettrage plumbing while this report is on screen
	return frappe.query_report && frappe.query_report.report_name === "Lettrage";
}

function lettrage_fmt(value) {
	return frappe.utils.format_number(flt(value), null, 3);
}

function lettrage_esc(value) {
	return frappe.utils.escape_html(cstr(value));
}

function lettrage_raw_filter(fieldname) {
	const field = frappe.query_report.get_filter(fieldname, false);
	return field ? field.value : undefined;
}

function lettrage_set_hidden_filter(fieldname, value) {
	// hidden filters have no visible input: get_filter_values() reads
	// f.value for them, so write the value straight on the control
	const field = frappe.query_report.get_filter(fieldname, false);
	if (field) field.value = value;
}

// ── bottom bar: page sizes + pagination (Ledger Data pattern) ────────────────
// the page number and the page size live in two HIDDEN filters; the server
// message ("Showing X - Y of N rows (page P of M).") is the only channel
// that carries the paging numbers — show_report_message is intercepted:
// the five integers are read positionally (the wording may be translated,
// the number order is not) and the native form-message above the table
// never shows for them.

const LETTRAGE_PAGINATION = {
	state: { page: 1, pages: 1, total: 0, start: 0, end: 0 },

	update_from_message(message) {
		const numbers = (message || "").match(/\d+/g) || [];
		if (numbers.length !== 5) return false;
		const [start, end, total, page, pages] = numbers.map(Number);
		this.state = { start, end, total, page, pages: Math.max(pages, 1) };
		return true;
	},

	reset_page() {
		lettrage_set_hidden_filter("page", 1);
		this.state.page = 1;
	},

	goto(page) {
		const pages = this.state.pages || 1;
		const target = Math.max(1, Math.min(Math.floor(page) || 1, pages));
		lettrage_set_hidden_filter("page", target);
		this.state.page = target;
		frappe.query_report.refresh();
	},

	set_page_size(size) {
		lettrage_set_hidden_filter("page_size", size);
		if (LETTRAGE) LETTRAGE.page_size = size;
		this.reset_page();
		frappe.query_report.refresh();
	},

	render($area) {
		if (!$area || !$area.length) return;
		const { page, pages, start, end, total } = this.state;
		if (!total) {
			$area.empty();
			return;
		}
		const page_size = LETTRAGE ? LETTRAGE.page_size : LETTRAGE_PAGE_SIZE;
		const size_buttons = LETTRAGE_PAGE_SIZES.map(
			(size) =>
				`<button type="button" class="btn btn-xs ${size === page_size ? "btn-primary" : "btn-default"} lettrage-page-size" data-size="${size}">${size}</button>`
		).join("");
		$area.html(
			`<span class="text-muted lettrage-showing">${__("Showing {0} - {1} of {2} rows", [
				start,
				end,
				total,
			])}</span>
			<span class="lettrage-sizes">${size_buttons}</span>
			<div class="btn-group lettrage-pages" role="group">
				<button type="button" class="btn btn-xs btn-default" data-lettrage-page="prev"${
					page <= 1 ? " disabled" : ""
				}>&larr;</button>
				<span class="text-muted lettrage-page-label">${__("Page {0} of {1}", [page, pages])}</span>
				<button type="button" class="btn btn-xs btn-default" data-lettrage-page="next"${
					page >= pages ? " disabled" : ""
				}>&rarr;</button>
			</div>`
		);
	},
};

// any real filter change restarts the pagination at page 1
function lettrage_filter_changed() {
	LETTRAGE_PAGINATION.reset_page();
	frappe.query_report.refresh(true);
}

// ── the report ───────────────────────────────────────────────────────────────

frappe.query_reports["Lettrage"] = {
	filters: [
		// panel / tab state: hidden filters driven by the account panel and
		// the status tabs (see the header comment)
		{
			fieldname: "account",
			label: __("Compte"),
			fieldtype: "Link",
			options: "Chart of Account",
			hidden: 1,
		},
		{
			fieldname: "tab",
			label: __("Statut"),
			fieldtype: "Select",
			options: LETTRAGE_TABS.join("\n"),
			default: "Non lettrees",
			hidden: 1,
		},
		{
			fieldname: "category",
			label: __("Categorie"),
			fieldtype: "Select",
			options: LETTRAGE_CATEGORIES.join("\n"),
			default: "Tous",
			hidden: 1,
		},
		{
			fieldname: "search",
			label: __("Recherche"),
			fieldtype: "Data",
			hidden: 1,
		},
		{
			fieldname: "hide_settled",
			label: __("Masquer les tiers soldes"),
			fieldtype: "Check",
			default: 1,
			hidden: 1,
		},
		// the old Filtres dialog: now the native visible filter bar
		{
			fieldname: "from_date",
			label: __("Du"),
			fieldtype: "Date",
			on_change: lettrage_filter_changed,
		},
		{
			fieldname: "to_date",
			label: __("Au"),
			fieldtype: "Date",
			on_change: lettrage_filter_changed,
		},
		{
			fieldname: "journal",
			label: __("Journal"),
			fieldtype: "Link",
			options: "Journal",
			on_change: lettrage_filter_changed,
		},
		{
			fieldname: "amount_min",
			label: __("Montant min"),
			fieldtype: "Float",
			on_change: lettrage_filter_changed,
		},
		{
			fieldname: "amount_max",
			label: __("Montant max"),
			fieldtype: "Float",
			on_change: lettrage_filter_changed,
		},
		{
			fieldname: "libelle",
			label: __("Libelle contient"),
			fieldtype: "Data",
			on_change: lettrage_filter_changed,
		},
		// pagination lives in client state: the page number and the page size
		// are hidden filters — never shown in the bar, still sent to the
		// server with every run (see LETTRAGE_PAGINATION above)
		{
			fieldname: "page_size",
			label: __("Lignes par page"),
			fieldtype: "Int",
			default: LETTRAGE_PAGE_SIZE,
			hidden: 1,
		},
		{
			fieldname: "page",
			label: __("Page"),
			fieldtype: "Int",
			default: 1,
			hidden: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		// the whole body is wrapped: ONE bad cell must never blank the table
		// (a throw inside a cell formatter aborts the virtual scroller's
		// chunk render). On error: log the column + row, fall back to the
		// default formatter, then to the escaped plain value.
		try {
			if (column.id === "solde_prog" && data) {
				// the running solde carries its D/C side as a chip
				const side = data.side || (flt(value) >= 0 ? "D" : "C");
				return `${lettrage_fmt(value)} <span class="lettrage-side-chip ${side}">${side}</span>`;
			}
			if (column.id === "lettrage" && data && data.lettrage_status === "Partiel") {
				return `${lettrage_esc(value)} (${__("Partiel")})`;
			}
			if (column.id === "pointe" && data) {
				// the interactive pointage toggle (treasury accounts, server-checked)
				return `<input type="checkbox" class="lettrage-pointe" data-name="${lettrage_esc(
					data.name
				)}" data-value="${data.pointe ? 0 : 1}"${data.pointe ? " checked" : ""}>`;
			}
			return default_formatter(value, row, column, data);
		} catch (error) {
			console.error(
				"lettrage: cell formatter failed for column",
				column && column.id,
				"row",
				row && row.meta ? row.meta.rowIndex : row,
				error
			);
			try {
				return default_formatter(value, row, column, data);
			} catch (fallback_error) {
				console.error("lettrage: default formatter failed too", fallback_error);
				return frappe.utils.escape_html(value == null ? "" : String(value));
			}
		}
	},

	onload(report) {
		// the live state: the panel state seeds from the hidden filters
		// (rebuilt from their defaults on every route entry)
		const hide_settled_raw = lettrage_raw_filter("hide_settled");
		LETTRAGE = {
			$layout: null,
			category: lettrage_raw_filter("category") || "Tous",
			search: lettrage_raw_filter("search") || "",
			hide_settled:
				hide_settled_raw === undefined || hide_settled_raw === "" || hide_settled_raw === null
					? 1
					: hide_settled_raw
						? 1
						: 0,
			sort_by: "numero",
			account: lettrage_raw_filter("account") || "",
			tab: lettrage_raw_filter("tab") || "Non lettrees",
			page_size: lettrage_raw_filter("page_size") || LETTRAGE_PAGE_SIZE,
			accounts: [],
			selection: {},
			columns: { mvt: 1, journal: 1, ref_doc: 1, libelle: 1, lettrage: 1, pointe: 1 },
			syncing: false,
		};

		lettrage_setup_css();
		lettrage_inject_layout(report);
		lettrage_setup_page_buttons(report);
		lettrage_bind_pointe(report);
		lettrage_bind_realtime();
		lettrage_bind_context_changes(report);
		lettrage_bind_bottom_bar(report);

		// Ledger Data's full-height treatment must not rule this page: it
		// re-adds its class on its own onload
		report.page.main.removeClass("report-gl-fill");
		// ... and its bottom bar (stale pagination of the last Grand Livre
		// query) must not leak onto this page — its own onload re-shows it
		report.page.main.children(".report-bottom-bar").hide();
		// its refresh wrapper dims its top summary bar on every refresh of
		// the shared singleton; undim after OUR refreshes too
		report.report_settings.after_refresh = () => {
			report.page.main.find(".report-summary-top").removeClass("gl-summary-loading");
		};

		// the datatable gets the row-selection checkbox column; the summary
		// cards and the totals stay global while the table pages
		report.report_settings.get_datatable_options = (options) =>
			Object.assign({}, options, { checkboxColumn: true, checkedRowStatus: false, layout: "fluid" });

		// column visibility (Affichage dialog): frappe's render filters
		// !col.hidden — re-apply the toggles BEFORE every render (this.columns
		// is rebuilt from the server response on every refresh). The wrapper
		// runs for EVERY report on the shared singleton: hands the datatable
		// back to the native layout when another report renders into it, and
		// only touches the columns while Lettrage is on screen.
		const render_datatable_original = report.render_datatable;
		report.render_datatable = function () {
			if (!lettrage_is_active()) {
				lettrage_unwrap(this);
				return render_datatable_original.apply(this, arguments);
			}
			lettrage_apply_column_hidden_flags(this.columns);
			return render_datatable_original.apply(this, arguments);
		};

		// after every render: re-apply the cross-page selection on the fresh
		// datatable data (the check map is keyed by index and survives a
		// datatable.refresh with stale values) and bind the check events once
		const previous_after_render = report.report_settings.after_datatable_render;
		report.report_settings.after_datatable_render = (datatable) => {
			if (previous_after_render) previous_after_render(datatable);
			if (!lettrage_is_active()) return;
			if (datatable && !datatable.__lettrage_bound) {
				datatable.__lettrage_bound = true;
				datatable.on("onCheckRow", () => {
					if (LETTRAGE && !LETTRAGE.syncing) lettrage_sync_selection();
				});
			}
			lettrage_reapply_selection_checks();
		};

		// the server message feeds the bottom bar pagination; paging numbers
		// never show above the table, any other message ("Pick an account on
		// the left.") shows natively — and then there is no summary to show
		report.show_report_message = (message) => {
			if (!lettrage_is_active()) {
				report.$report_message.html(message || "").toggle(!!message);
				return;
			}
			if (LETTRAGE_PAGINATION.update_from_message(message)) {
				report.$report_message.hide();
				report.$summary.show();
			} else if (message) {
				report.$report_message.html(message).show();
				report.$summary.hide();
			} else {
				report.$report_message.hide();
			}
			LETTRAGE_PAGINATION.render(LETTRAGE.$layout.find("#lettrage-bottom-bar"));
		};

		// an empty run leaves the previous page of numbers in the bar: clear
		// it when the native "no result" state shows
		const toggle_nothing_original = report.toggle_nothing_to_show;
		report.toggle_nothing_to_show = function (flag) {
			if (flag && lettrage_is_active() && LETTRAGE.$layout) {
				LETTRAGE_PAGINATION.state = { page: 1, pages: 1, total: 0, start: 0, end: 0 };
				LETTRAGE_PAGINATION.render(LETTRAGE.$layout.find("#lettrage-bottom-bar"));
			}
			return toggle_nothing_original.apply(this, arguments);
		};

		// the title carries the context: "MEDDEB · EX 2026"
		lettrage_set_title(report);

		// the panel loads immediately; the report itself refreshes right
		// after onload
		lettrage_load_accounts();
	},
};

// ── layout / css ─────────────────────────────────────────────────────────────

function lettrage_setup_css() {
	if (document.getElementById("lettrage-report-css")) return;
	$(
		`<style id="lettrage-report-css">
			.lettrage-layout { display: flex; gap: 12px; align-items: stretch; }
			.lettrage-left { width: 300px; min-width: 240px; border: 1px solid var(--border-color); border-radius: 8px; display: flex; flex-direction: column; }
			.lettrage-left.collapsed { width: 44px; min-width: 44px; cursor: pointer; }
			.lettrage-left.collapsed .lettrage-left-body { display: none; }
			.lettrage-left-body { padding: 10px; overflow-y: auto; flex: 1; max-height: calc(100vh - 260px); }
			.lettrage-cat-tabs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
			.lettrage-cat-tabs button { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
			.lettrage-cat-tabs button.active { background: var(--brand-primary, #2490ef); color: #fff; }
			.lettrage-overview { border: 1px solid var(--border-color); border-radius: 6px; padding: 8px; margin: 8px 0; font-size: 12px; }
			.lettrage-account-card { border: 1px solid var(--border-color); border-radius: 6px; padding: 8px; margin-bottom: 6px; cursor: pointer; }
			.lettrage-account-card:hover { background: var(--control-bg, #f8f8f8); }
			.lettrage-account-card.active { border-color: var(--brand-primary, #2490ef); }
			.lettrage-account-card .acc-num { font-weight: 700; font-size: 12px; }
			.lettrage-account-card .acc-name { font-size: 12px; color: var(--text-muted); }
			.lettrage-chip { display: inline-block; font-size: 10px; border-radius: 10px; padding: 1px 7px; background: var(--bg-orange, #ffd8a8); color: #8a4b00; }
			.lettrage-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
			.lettrage-right-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; min-height: 24px; }
			.lettrage-progress { margin-top: 4px; width: 100%; }
			.lettrage-tabs { display: flex; gap: 4px; margin: 8px 0; }
			.lettrage-tabs button { font-size: 11px; padding: 2px 10px; border-radius: 12px; }
			.lettrage-tabs button.active { background: var(--brand-primary, #2490ef); color: #fff; }
			.lettrage-jrn-chip { background: var(--bg-blue, #e2eaff); border-radius: 8px; padding: 0 6px; font-size: 10px; font-weight: 600; }
			.lettrage-side-chip { border-radius: 8px; padding: 0 5px; font-size: 10px; font-weight: 700; }
			.lettrage-side-chip.D { background: #e6f4ea; color: #1a7f37; }
			.lettrage-side-chip.C { background: #fdecec; color: #c0392b; }
			.lettrage-bottom-bar { display: flex; gap: 14px; align-items: center; justify-content: flex-end; padding: 6px 0; flex-wrap: wrap; }
			.lettrage-pages { display: inline-flex; gap: 6px; align-items: center; }
			.lettrage-actions-bar { position: sticky; bottom: 0; background: var(--card-bg, #fff); border: 1px solid var(--border-color); border-radius: 6px; padding: 6px 10px; display: flex; gap: 10px; align-items: center; z-index: 4; }
			.lettrage-footer { display: flex; gap: 8px; align-items: center; margin-top: 6px; font-size: 11px; color: var(--text-muted); }
		</style>`
	).appendTo("head");
}

function lettrage_inject_layout(report) {
	// wrap the datatable: the panel goes on the left, the account head + tabs
	// above it, the bottom bar + the sticky selection bar under it. The page
	// is shared by every query report, so lettrage_unwrap hands the datatable
	// back before another report renders into it — this re-wrap reuses the
	// layout element when coming back within the session.
	const $existing = report.page.main.find(".lettrage-layout");
	if ($existing.length) {
		$existing.insertBefore(report.$report);
		$existing.find(".lettrage-main").append(report.$report);
		$existing.show();
		LETTRAGE.$layout = $existing;
		lettrage_bind_shell($existing);
		lettrage_sync_panel_inputs($existing);
		lettrage_render_tabs();
		lettrage_render_account_head();
		return;
	}
	const $layout = $(`
		<div class="lettrage-layout">
			<div class="lettrage-left" id="lettrage-left">
				<div class="lettrage-left-body">
					<div class="lettrage-cat-tabs" id="lettrage-cats"></div>
					<input type="text" class="form-control form-control-sm" id="lettrage-search"
						placeholder="${__("Code ou nom du compte")}">
					<div class="checkbox" style="margin: 6px 0;">
						<label><input type="checkbox" id="lettrage-hide-settled" checked>
							${__("Masquer les tiers soldes")}</label>
					</div>
					<div style="display:flex; gap:4px; margin-bottom:8px;">
						<button class="btn btn-xs btn-default tu-sort" data-sort="numero">${__("N° compte")}</button>
						<button class="btn btn-xs btn-default tu-sort" data-sort="montant">${__("Montant")}</button>
						<button class="btn btn-xs btn-default tu-sort" data-sort="libelle">${__("Libelle")}</button>
					</div>
					<div class="lettrage-overview" id="lettrage-overview"></div>
					<div id="lettrage-accounts"></div>
					<div class="lettrage-footer" id="lettrage-left-footer"></div>
				</div>
			</div>
			<div class="lettrage-main">
				<div class="lettrage-right-head">
					<div id="lettrage-account-head"></div>
					<div class="lettrage-progress" id="lettrage-progress"></div>
				</div>
				<div class="lettrage-tabs" id="lettrage-line-tabs"></div>
				<div class="lettrage-bottom-bar" id="lettrage-bottom-bar"></div>
				<div id="lettrage-selection-bar"></div>
			</div>
		</div>
	`);
	report.$report.before($layout);
	// the datatable moves into the right column (the element stays the same,
	// frappe re-renders into it on every refresh)
	$layout.find(".lettrage-main").append(report.$report);
	LETTRAGE.$layout = $layout;
	lettrage_bind_shell($layout);
	lettrage_sync_panel_inputs($layout);
	lettrage_render_tabs();
	lettrage_render_account_head();
}

function lettrage_unwrap(report) {
	// another report renders into the shared page: hand the datatable back
	// to page.main and hide the lettrage chrome (the wrapper keeps the
	// element — coming back to Lettrage re-wraps without a rebuild)
	if (!LETTRAGE || !LETTRAGE.$layout) return;
	if ($.contains(LETTRAGE.$layout[0], report.$report[0])) {
		LETTRAGE.$layout.insertBefore(report.$report);
	}
	LETTRAGE.$layout.hide();
}

function lettrage_sync_panel_inputs($layout) {
	// the route re-entry rebuilds the state from the filter defaults: the
	// kept layout DOM must match
	$layout.find("#lettrage-search").val(LETTRAGE.search || "");
	$layout.find("#lettrage-hide-settled").prop("checked", !!LETTRAGE.hide_settled);
}

// ── header buttons ───────────────────────────────────────────────────────────

function lettrage_setup_page_buttons(report) {
	// page.clear_inner_toolbar() ran before onload: re-adding is safe
	report.page.set_primary_action(__("Lettrage automatique"), () => lettrage_run_auto("lettrage"));
	report.page.add_inner_button(__("Delettrage automatique"), () => {
		frappe.confirm(__("Delettrer tous les groupes automatiques de la selection ?"), () =>
			lettrage_run_auto("delettrage")
		);
	});
	report.page.add_inner_button(__("Suggerer"), () => lettrage_show_suggestions());
	report.page.add_inner_button(__("Filtres"), () => {
		// the visible filter bar toggles (the old Filtres dialog is native now)
		const $form = report.page.page_form;
		if ($form.is(":visible")) report.page.hide_form();
		else report.page.show_form();
	});
	report.page.add_inner_button(__("Affichage"), () => lettrage_show_columns_dialog());
	report.page.add_inner_button(__("Refresh"), () => frappe.query_report.refresh());
}

function lettrage_run_auto(kind) {
	frappe.call({
		method: LETTRAGE_API + (kind === "lettrage" ? "run_auto_lettrage" : "run_auto_delettrage"),
		args: {
			category: LETTRAGE.category,
			account: LETTRAGE.account || "ALL",
			rules: JSON.stringify(["R1", "R2"]),
		},
		callback() {
			frappe.show_alert({ message: __("Lettrage automatique lance."), indicator: "blue" });
		},
	});
}

// ── realtime progress (unchanged event name: lettrage_progress) ──────────────

function lettrage_bind_realtime() {
	if (frappe._lettrage_realtime_bound) return;
	frappe._lettrage_realtime_bound = true;
	frappe.realtime.on("lettrage_progress", (data) => {
		const $progress = LETTRAGE && LETTRAGE.$layout ? LETTRAGE.$layout.find("#lettrage-progress") : $();
		if (!$progress.length || !data) return;
		if (data.phase === "run") {
			$progress.html(
				`<div class="progress"><div class="progress-bar" style="width:${data.progress}%"></div></div>
				<div class="text-muted" style="font-size:11px;">${__("Lettrage {0}% — {1} groupe(s), {2} ligne(s)", [
					data.progress,
					data.groups || 0,
					data.lines || 0,
				])}</div>`
			);
		} else {
			$progress.html(
				`<div class="text-muted" style="font-size:11px;">${__(
					"Termine: {0} groupe(s), {1} ligne(s) lettrees, {2} ignoree(s).",
					[data.groups || 0, data.lines || 0, data.skipped || 0]
				)}</div>`
			);
			if (LETTRAGE && lettrage_is_active()) {
				lettrage_load_accounts();
				frappe.query_report.refresh();
			}
		}
	});
}

// a dock context switch re-runs the report and the panel
function lettrage_bind_context_changes(report) {
	$(document)
		.off("axeane-context-changed.lettrage-report")
		.on("axeane-context-changed.lettrage-report", () => {
			if (!LETTRAGE || !LETTRAGE.$layout || !LETTRAGE.$layout.is(":visible")) return;
			LETTRAGE.selection = {};
			lettrage_set_title(report);
			lettrage_load_accounts();
			frappe.query_report.refresh();
		});
}

function lettrage_set_title(report) {
	const ctx = (window.axeane && axeane.context && axeane.context.get()) || {};
	if (ctx.entreprise_label || ctx.exercice_label) {
		report.page.set_title(
			__("Lettrage") + " · " + [ctx.entreprise_label, ctx.exercice_label].filter(Boolean).join(" · ")
		);
	}
}

// ── account panel ────────────────────────────────────────────────────────────

function lettrage_bind_shell($layout) {
	$layout.find("#lettrage-left").off("click.lettrage-collapse").on("click.lettrage-collapse", (e) => {
		if ($(e.target).closest("input, button, .lettrage-account-card").length) return;
		$layout.find("#lettrage-left").toggleClass("collapsed");
	});
	$layout.find("#lettrage-search")
		.off("input.lettrage-search")
		.on(
			"input.lettrage-search",
			frappe.utils.debounce(() => {
				LETTRAGE.search = $layout.find("#lettrage-search").val() || "";
				lettrage_set_hidden_filter("search", LETTRAGE.search);
				lettrage_load_accounts();
			}, 300)
		);
	$layout.find("#lettrage-hide-settled")
		.off("change.lettrage-hide-settled")
		.on("change.lettrage-hide-settled", (e) => {
			LETTRAGE.hide_settled = e.target.checked ? 1 : 0;
			lettrage_set_hidden_filter("hide_settled", LETTRAGE.hide_settled);
			lettrage_load_accounts();
		});
	$layout.find(".tu-sort")
		.off("click.lettrage-sort")
		.on("click.lettrage-sort", (e) => {
			LETTRAGE.sort_by = $(e.currentTarget).data("sort");
			lettrage_load_accounts();
		});
}

function lettrage_load_accounts() {
	if (!LETTRAGE || !LETTRAGE.$layout) return;
	frappe.call({
		method: LETTRAGE_API + "get_accounts",
		args: {
			category: LETTRAGE.category,
			search: LETTRAGE.search || "",
			hide_settled: LETTRAGE.hide_settled,
			sort_by: LETTRAGE.sort_by,
		},
		callback(r) {
			if (!LETTRAGE) return;
			const message = r.message || { accounts: [], totals: {} };
			LETTRAGE.accounts = message.accounts || [];
			lettrage_render_categories();
			lettrage_render_overview(message.totals || {});
			lettrage_render_accounts(LETTRAGE.accounts);
			lettrage_render_account_head();
		},
	});
}

function lettrage_render_categories() {
	const html = LETTRAGE_CATEGORIES.map((cat) => {
		const label = cat === "Debiteurs-Crediteurs" ? __("Debiteurs-Crediteurs") : __(cat);
		return `<button class="btn btn-xs btn-default ${LETTRAGE.category === cat ? "active" : ""}" data-cat="${lettrage_esc(cat)}">${label}</button>`;
	}).join("");
	const $tabs = LETTRAGE.$layout.find("#lettrage-cats");
	$tabs.html(html);
	$tabs.find("button")
		.off("click")
		.on("click", (e) => {
			LETTRAGE.category = $(e.currentTarget).data("cat");
			lettrage_set_hidden_filter("category", LETTRAGE.category);
			// a category switch drops the selected account (like the old tool)
			LETTRAGE.account = "";
			lettrage_set_hidden_filter("account", "");
			LETTRAGE.selection = {};
			lettrage_render_tabs();
			lettrage_render_account_head();
			lettrage_load_accounts();
			frappe.query_report.refresh();
		});
}

function lettrage_render_overview(totals) {
	LETTRAGE.$layout.find("#lettrage-overview").html(
		`<b>${__("Vue d'ensemble")}</b><br>
		${__("{0} compte(s)", [totals.account_count || 0])} ·
		${__("total {0} a lettrer", [totals.total_a_lettrer || 0])}
		${totals.hidden_settled ? ` · ${__("{0} solde(s) masque(s)", [totals.hidden_settled])}` : ""}`
	);
	LETTRAGE.$layout.find("#lettrage-left-footer").html(
		`${__(" {0} compte(s)", [totals.account_count || 0])} · ${__(" {0} solde(s) masque(s)", [
			totals.hidden_settled || 0,
		])}`
	);
}

function lettrage_render_accounts(accounts) {
	const $wrap = LETTRAGE.$layout.find("#lettrage-accounts");
	if (!accounts.length) {
		$wrap.html(`<div class="text-muted" style="padding:8px 0;">${__("No account to letter.")}</div>`);
		return;
	}
	$wrap.html(
		accounts
			.map(
				(account) => `
			<div class="lettrage-account-card ${LETTRAGE.account === account.account ? "active" : ""}" data-account="${lettrage_esc(account.account)}">
				<div style="display:flex; justify-content:space-between; gap:6px;">
					<span class="acc-num">${lettrage_esc(account.number)}</span>
					<span class="acc-num">${lettrage_fmt(account.solde)} ${account.side}</span>
				</div>
				<div style="display:flex; justify-content:space-between; gap:6px;">
					<span class="acc-name">${lettrage_esc(account.name)}</span>
					${account.a_lettrer ? `<span class="lettrage-chip">${__(" {0} a lettrer", [account.a_lettrer])}</span>` : ""}
				</div>
			</div>`
			)
			.join("")
	);
	$wrap.find(".lettrage-account-card")
		.off("click")
		.on("click", (e) => {
			const name = $(e.currentTarget).data("account");
			// clicking a card sets the account; clicking the active card again
			// clears it (the only way back to the empty state)
			LETTRAGE.account = LETTRAGE.account === name ? "" : name;
			lettrage_set_hidden_filter("account", LETTRAGE.account);
			LETTRAGE.selection = {};
			LETTRAGE_PAGINATION.reset_page();
			lettrage_render_accounts(LETTRAGE.accounts);
			lettrage_render_account_head();
			frappe.query_report.refresh();
		});
}

// ── right head + tabs ────────────────────────────────────────────────────────

function lettrage_render_account_head() {
	const $head = LETTRAGE.$layout.find("#lettrage-account-head");
	if (!LETTRAGE.account) {
		$head.html(`<div class="text-muted">${__("Pick an account on the left.")}</div>`);
		return;
	}
	const meta = (LETTRAGE.accounts || []).find((a) => a.account === LETTRAGE.account);
	const name = meta ? meta.name : String(LETTRAGE.account).split(" - ")[0];
	$head.html(
		`<b style="font-size:13px;">${lettrage_esc(name)}</b>
		<span class="lettrage-jrn-chip">${lettrage_esc(LETTRAGE.account)}</span>`
	);
}

function lettrage_render_tabs() {
	const $tabs = LETTRAGE.$layout.find("#lettrage-line-tabs");
	$tabs.html(
		LETTRAGE_TABS.map(
			(tab) =>
				`<button class="btn btn-xs btn-default ${LETTRAGE.tab === tab ? "active" : ""}" data-tab="${lettrage_esc(tab)}">${__(tab)}</button>`
		).join("")
	);
	$tabs.find("button")
		.off("click")
		.on("click", (e) => {
			LETTRAGE.tab = $(e.currentTarget).data("tab");
			lettrage_set_hidden_filter("tab", LETTRAGE.tab);
			LETTRAGE.selection = {};
			LETTRAGE_PAGINATION.reset_page();
			lettrage_render_tabs();
			frappe.query_report.refresh();
		});
}

// ── selection (datatable checkbox column) ────────────────────────────────────

function lettrage_sync_selection() {
	const datatable = frappe.query_report.datatable;
	if (!datatable || !datatable.rowmanager || !LETTRAGE) return;
	const checked = new Set(datatable.rowmanager.getCheckedRows().map(Number));
	(frappe.query_report.data || []).forEach((row, index) => {
		if (!row || !row.name) return;
		if (checked.has(index)) LETTRAGE.selection[row.name] = row;
		else delete LETTRAGE.selection[row.name];
	});
	lettrage_render_selection_bar();
}

function lettrage_reapply_selection_checks() {
	const datatable = frappe.query_report.datatable;
	if (!datatable || !datatable.rowmanager || !LETTRAGE) return;
	LETTRAGE.syncing = true;
	try {
		// the check map survives a datatable.refresh keyed by index: clear it
		// and re-check the rows still in the selection (across pages)
		datatable.rowmanager.checkAll(false);
		(frappe.query_report.data || []).forEach((row, index) => {
			if (row && row.name && LETTRAGE.selection[row.name]) {
				datatable.rowmanager.checkRow(index, true);
			}
		});
	} finally {
		LETTRAGE.syncing = false;
	}
	lettrage_render_selection_bar();
}

function lettrage_selection_totals() {
	const names = Object.keys(LETTRAGE.selection);
	let debit = 0;
	let credit = 0;
	names.forEach((name) => {
		debit += flt(LETTRAGE.selection[name].debit);
		credit += flt(LETTRAGE.selection[name].credit);
	});
	return { names, debit: flt(debit, 3), credit: flt(credit, 3), ecart: flt(debit - credit, 3) };
}

function lettrage_render_selection_bar() {
	const $bar = LETTRAGE.$layout.find("#lettrage-selection-bar");
	const { names, debit, credit, ecart } = lettrage_selection_totals();
	if (!names.length) {
		$bar.empty();
		return;
	}
	$bar.html(
		`<div class="lettrage-actions-bar">
			<b>${__("Lettrer ({0})", [names.length])}</b>
			<span>${__("Debit {0}", [lettrage_fmt(debit)])} · ${__("Credit {0}", [lettrage_fmt(credit)])} ·
				Ecart <b class="${ecart ? "text-danger" : "text-success"}">${lettrage_fmt(ecart)}</b></span>
			<button class="btn btn-primary btn-sm tu-letter">${__("Lettrer")}</button>
			<button class="btn btn-sm tu-unletter" style="border:1px solid var(--text-on-red, #c0392b); color: var(--text-on-red, #c0392b);">${__(
				"Delettrer"
			)}</button>
		</div>`
	);
	$bar.find(".tu-letter").on("click", () => {
		const allow_partial = Math.abs(ecart) > LETTRAGE_TOLERANCE ? 1 : 0;
		if (allow_partial) {
			frappe.confirm(
				__("Lettrage partiel ? L'ecart de {0} restera en Partiel.", [lettrage_fmt(ecart)]),
				() => lettrage_letter_selection(names, allow_partial)
			);
		} else {
			lettrage_letter_selection(names, 0);
		}
	});
	$bar.find(".tu-unletter").on("click", () => {
		frappe.call({
			method: LETTRAGE_API + "unletter",
			args: { names: JSON.stringify(names) },
			callback() {
				LETTRAGE.selection = {};
				lettrage_refresh_all();
			},
		});
	});
}

function lettrage_letter_selection(names, allow_partial) {
	frappe.call({
		method: LETTRAGE_API + "letter_lines",
		args: {
			account: LETTRAGE.account,
			names: JSON.stringify(names),
			allow_partial: allow_partial,
		},
		callback(r) {
			const message = r.message || {};
			LETTRAGE.selection = {};
			frappe.show_alert({
				message: __("Lettre {0}: {1} ligne(s), ecart {2}.", [message.code, message.count, lettrage_fmt(message.ecart)]),
				indicator: message.status === "Lettre" ? "green" : "orange",
			});
			lettrage_refresh_all();
		},
	});
}

/** The tool's own refresh after a write: the report re-runs (the datatable
 * re-render re-applies the selection checks) and the panel reloads. */
function lettrage_refresh_all() {
	lettrage_load_accounts();
	frappe.query_report.refresh();
}

// ── pointage ─────────────────────────────────────────────────────────────────

function lettrage_bind_pointe(report) {
	// the POINTE checkboxes are rendered by the cell formatter; the binding
	// is delegated (the datatable re-renders cells on every refresh)
	report.$report
		.off("change.lettrage-pointe")
		.on("change.lettrage-pointe", ".lettrage-pointe", function (event) {
			event.stopPropagation();
			frappe.call({
				method: LETTRAGE_API + "toggle_pointe",
				args: { names: JSON.stringify([$(this).data("name")]), value: $(this).data("value") },
				callback() {
					frappe.query_report.refresh();
				},
			});
		});
}

// ── bottom bar bindings ──────────────────────────────────────────────────────

function lettrage_bind_bottom_bar(report) {
	report.page.main
		.off("click.lettrage-pages", ".lettrage-pages button")
		.on("click.lettrage-pages", ".lettrage-pages button", function (event) {
			event.preventDefault();
			if (this.disabled) return;
			const target = $(this).attr("data-lettrage-page");
			const { page, pages } = LETTRAGE_PAGINATION.state;
			if (target === "prev") LETTRAGE_PAGINATION.goto(page - 1);
			else if (target === "next") LETTRAGE_PAGINATION.goto(page + 1);
		});
	report.page.main
		.off("click.lettrage-page-size", ".lettrage-page-size")
		.on("click.lettrage-page-size", ".lettrage-page-size", function (event) {
			event.preventDefault();
			LETTRAGE_PAGINATION.set_page_size($(this).data("size"));
		});
}

// ── dialogs ──────────────────────────────────────────────────────────────────

function lettrage_show_suggestions() {
	if (!LETTRAGE.account) return;
	frappe.call({
		method: LETTRAGE_API + "suggest",
		args: { account: LETTRAGE.account },
		callback(r) {
			const candidates = (r.message && r.message.candidates) || [];
			if (!candidates.length) {
				frappe.msgprint({ title: __("Suggerer"), message: __("No balancing set found."), indicator: "orange" });
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Suggerer"),
				size: "large",
				fields: [
					{
						fieldname: "candidate",
						fieldtype: "Select",
						label: __("Ensemble"),
						options: candidates
							.map((c, i) => `${i}:${c.rule} ${c.key} (${c.count} ${__("lignes")}, ${lettrage_fmt(c.total_debit)})`)
							.join("\n"),
						reqd: 1,
					},
				],
				primary_action_label: __("Lettrer"),
				primary_action(values) {
					const index = parseInt(values.candidate, 10);
					const candidate = candidates[index];
					d.hide();
					frappe.call({
						method: LETTRAGE_API + "letter_lines",
						args: {
							account: LETTRAGE.account,
							names: JSON.stringify(candidate.names),
							allow_partial: 0,
						},
						callback() {
							frappe.show_alert({ message: __("Lettrer OK."), indicator: "green" });
							lettrage_refresh_all();
						},
					});
				},
			});
			d.show();
		},
	});
}

function lettrage_show_columns_dialog() {
	const labels = {
		mvt: __("MVT"),
		journal: __("JRN"),
		ref_doc: __("N° PIECE"),
		libelle: __("LIBELLE"),
		lettrage: __("LETTRE"),
		pointe: __("POINTE"),
	};
	const d = new frappe.ui.Dialog({
		title: __("Affichage"),
		fields: Object.keys(labels).map((fieldname) => ({
			fieldname: fieldname,
			fieldtype: "Check",
			label: labels[fieldname],
			default: LETTRAGE.columns[fieldname] ? 1 : 0,
		})),
		primary_action_label: __("OK"),
		primary_action(values) {
			d.hide();
			Object.assign(LETTRAGE.columns, values || {});
			// the wrapped render_datatable re-applies the hidden flags first
			frappe.query_report.render_datatable();
		},
	});
	d.show();
}

function lettrage_apply_column_hidden_flags(columns) {
	if (!columns || !LETTRAGE) return;
	columns.forEach((column) => {
		if (column.fieldname in LETTRAGE.columns) {
			column.hidden = LETTRAGE.columns[column.fieldname] ? 0 : 1;
		}
	});
}
