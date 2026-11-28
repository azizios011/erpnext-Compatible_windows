// Copyright (c) 2026, Frappe Technologies Pty. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

// "Lettrage" — the Saisie du lettrage tool as a Script Report. Left: the
// account panel (category chips, search, hide-settled, sort, per-account
// solde + unmatched count). Right: the account head, the status tabs, the
// line table and the bottom pagination bar. A sticky action bar carries the
// live selection: Lettrer (balanced only), Partiel, Delettrer, Suggerer and
// the auto passes. Selecting a lettered line pulls its whole group in.
// Every write goes through lettrage_api.py; rows locked by a clotured
// Déclaration Mensuelle are rejected server-side and shown locked here.

const LETTRAGE_API = "erpnext.custom_modules.reports.lettrage_api.";
const LETTRAGE_CATEGORIES = ["Tous", "Clients", "Fournisseurs", "Salaries", "Debiteurs-Crediteurs", "Autres"];
const LETTRAGE_TABS = ["Non lettrees", "Partielles", "Lettrees", "Toutes"];
const LETTRAGE_PAGE_SIZES = [15, 25, 50, 100, 250];
const LETTRAGE_PAGE_SIZE = 25;
const LETTRAGE_TOLERANCE = 0.001;
const LETTRAGE_TREASURY_TYPES = ["Bank", "Cash"];

// live state — rebuilt on every onload (route re-entry), null before
let LETTRAGE = null;

function lettrage_is_active() {
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
	const field = frappe.query_report.get_filter(fieldname, false);
	if (field) field.value = value;
}

function lettrage_side_chip(value) {
	const side = flt(value) >= 0 ? "D" : "C";
	const css = side === "D" ? "indicator-green" : "indicator-red";
	return `${lettrage_fmt(value)} <span class="indicator-pill no-indicator-icon ${css}">${side}</span>`;
}

// ── bottom bar: page sizes + pagination (Ledger Data pattern) ────────────────

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

function lettrage_filter_changed() {
	LETTRAGE_PAGINATION.reset_page();
	frappe.query_report.refresh(true);
}

// ── the report definition ────────────────────────────────────────────────────

frappe.query_reports["Lettrage"] = {
	filters: [
		{ fieldname: "account", label: __("Compte"), fieldtype: "Link", options: "Chart of Account", hidden: 1 },
		{ fieldname: "tab", label: __("Statut"), fieldtype: "Select", options: LETTRAGE_TABS.join("\n"), default: "Non lettrees", hidden: 1 },
		{ fieldname: "category", label: __("Categorie"), fieldtype: "Select", options: LETTRAGE_CATEGORIES.join("\n"), default: "Tous", hidden: 1 },
		{ fieldname: "search", label: __("Recherche"), fieldtype: "Data", hidden: 1 },
		{ fieldname: "hide_settled", label: __("Masquer les tiers soldes"), fieldtype: "Check", default: 1, hidden: 1 },
		{ fieldname: "from_date", label: __("Du"), fieldtype: "Date", on_change: lettrage_filter_changed },
		{ fieldname: "to_date", label: __("Au"), fieldtype: "Date", on_change: lettrage_filter_changed },
		{ fieldname: "journal", label: __("Journal"), fieldtype: "Link", options: "Journal", on_change: lettrage_filter_changed },
		{ fieldname: "amount_min", label: __("Montant min"), fieldtype: "Float", on_change: lettrage_filter_changed },
		{ fieldname: "amount_max", label: __("Montant max"), fieldtype: "Float", on_change: lettrage_filter_changed },
		{ fieldname: "libelle", label: __("Libelle contient"), fieldtype: "Data", on_change: lettrage_filter_changed },
		{ fieldname: "page_size", label: __("Lignes par page"), fieldtype: "Int", default: LETTRAGE_PAGE_SIZE, hidden: 1 },
		{ fieldname: "page", label: __("Page"), fieldtype: "Int", default: 1, hidden: 1 },
	],

	formatter(value, row, column, data, default_formatter) {
		// ONE bad cell must never blank the table: log, then fall back
		try {
			if (!data) return default_formatter(value, row, column, data);
			if (column.id === "solde_prog") return lettrage_side_chip(value);
			if (column.id === "lettrage") {
				const lock = data.declaration_cloture
					? ` <span class="indicator-pill no-indicator-icon indicator-gray" title="${lettrage_esc(
							data.declaration_cloture
						)}">🔒</span>`
					: "";
				const partial = data.lettrage_status === "Partiel" ? ` (${__("Partiel")})` : "";
				return `${lettrage_esc(value)}${partial}${lock}`;
			}
			if (column.id === "pointe") {
				if (!LETTRAGE_TREASURY_TYPES.includes(data.account_type)) return "";
				return `<input type="checkbox" class="lettrage-pointe" data-name="${lettrage_esc(
					data.name
				)}" data-value="${data.pointe ? 0 : 1}"${data.pointe ? " checked" : ""}>`;
			}
			return default_formatter(value, row, column, data);
		} catch (error) {
			console.error("lettrage: cell formatter failed for column", column && column.id, error);
			try {
				return default_formatter(value, row, column, data);
			} catch (fallback_error) {
				console.error("lettrage: default formatter failed too", fallback_error);
				return frappe.utils.escape_html(value == null ? "" : String(value));
			}
		}
	},

	onload(report) {
		const hide_settled_raw = lettrage_raw_filter("hide_settled");
		LETTRAGE = {
			$layout: null,
			category: lettrage_raw_filter("category") || "Tous",
			search: lettrage_raw_filter("search") || "",
			hide_settled: hide_settled_raw === undefined || hide_settled_raw === "" ? 1 : hide_settled_raw ? 1 : 0,
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

		report.page.main.removeClass("report-gl-fill");
		report.page.main.children(".report-bottom-bar").hide();
		report.report_settings.after_refresh = () => {
			report.page.main.find(".report-summary-top").removeClass("gl-summary-loading");
		};

		report.report_settings.get_datatable_options = (options) =>
			Object.assign({}, options, { checkboxColumn: true, checkedRowStatus: false, layout: "fluid" });

		const render_datatable_original = report.render_datatable;
		report.render_datatable = function () {
			if (!lettrage_is_active()) {
				lettrage_unwrap(this);
				return render_datatable_original.apply(this, arguments);
			}
			lettrage_apply_column_hidden_flags(this.columns);
			return render_datatable_original.apply(this, arguments);
		};

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
			lettrage_reapply_checks();
		};

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

		const toggle_nothing_original = report.toggle_nothing_to_show;
		report.toggle_nothing_to_show = function (flag) {
			if (flag && lettrage_is_active() && LETTRAGE.$layout) {
				LETTRAGE_PAGINATION.state = { page: 1, pages: 1, total: 0, start: 0, end: 0 };
				LETTRAGE_PAGINATION.render(LETTRAGE.$layout.find("#lettrage-bottom-bar"));
			}
			return toggle_nothing_original.apply(this, arguments);
		};

		lettrage_set_title(report);
		lettrage_load_accounts();
	},
};

// ── CSS — desk variables only (light and dark follow the theme) ──────────────

function lettrage_setup_css() {
	if (document.getElementById("lettrage-report-css")) return;
	$(
		`<style id="lettrage-report-css">
			.lettrage-layout { display: flex; gap: 12px; align-items: stretch; }
			.lettrage-left { width: 300px; min-width: 240px; border: 1px solid var(--border-color); border-radius: var(--border-radius-lg, 8px); background: var(--card-bg); display: flex; flex-direction: column; }
			.lettrage-left.collapsed { width: 44px; min-width: 44px; cursor: pointer; }
			.lettrage-left.collapsed .lettrage-left-body { display: none; }
			.lettrage-left-body { padding: 10px; overflow-y: auto; flex: 1; max-height: calc(100vh - 260px); }
			.lettrage-cat-tabs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
			.lettrage-cat-tabs button { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
			.lettrage-overview { border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 6px); padding: 8px; margin: 8px 0; font-size: 12px; }
			.lettrage-account-card { border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 6px); padding: 8px; margin-bottom: 6px; cursor: pointer; }
			.lettrage-account-card:hover { background: var(--control-bg); }
			.lettrage-account-card.active { border-color: var(--brand-primary); }
			.lettrage-account-card .acc-num { font-weight: 700; font-size: 12px; }
			.lettrage-account-card .acc-name { font-size: 12px; color: var(--text-muted); }
			.lettrage-chip { display: inline-block; font-size: 10px; border-radius: 10px; padding: 1px 7px; background: var(--bs-warning-bg-subtle); color: var(--bs-warning-text-emphasis); }
			.lettrage-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
			.lettrage-right-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; min-height: 24px; }
			.lettrage-progress { margin-top: 4px; width: 100%; }
			.lettrage-tabs { display: flex; gap: 4px; margin: 8px 0; }
			.lettrage-tabs button { font-size: 11px; padding: 2px 10px; border-radius: 12px; }
			.lettrage-jrn-chip { background: var(--bs-info-bg-subtle); border-radius: 8px; padding: 0 6px; font-size: 10px; font-weight: 600; }
			.lettrage-actions-bar { position: sticky; bottom: 0; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 6px); padding: 6px 10px; display: flex; gap: 10px; align-items: center; z-index: 4; flex-wrap: wrap; }
			.lettrage-footer { display: flex; gap: 8px; align-items: center; margin-top: 6px; font-size: 11px; color: var(--text-muted); }
		</style>`
	).appendTo("head");
}

// ── layout injection ─────────────────────────────────────────────────────────

function lettrage_inject_layout(report) {
	const $existing = report.page.main.find(".lettrage-layout");
	if ($existing.length) {
		$existing.insertBefore(report.$report);
		$existing.find(".lettrage-main").append(report.$report);
		// the action bar must sit AFTER the table for its sticky-bottom to
		// pin it while the long table scrolls (the old bar sat above it and
		// scrolled away)
		$existing.find("#lettrage-selection-bar").insertAfter(report.$report);
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
	$layout.find(".lettrage-main").append(report.$report);
	$layout.find("#lettrage-selection-bar").insertAfter(report.$report);
	LETTRAGE.$layout = $layout;
	lettrage_bind_shell($layout);
	lettrage_sync_panel_inputs($layout);
	lettrage_render_tabs();
	lettrage_render_account_head();
}

function lettrage_unwrap(report) {
	if (!LETTRAGE || !LETTRAGE.$layout) return;
	if ($.contains(LETTRAGE.$layout[0], report.$report[0])) {
		LETTRAGE.$layout.insertBefore(report.$report);
	}
	LETTRAGE.$layout.hide();
}

function lettrage_sync_panel_inputs($layout) {
	$layout.find("#lettrage-search").val(LETTRAGE.search || "");
	$layout.find("#lettrage-hide-settled").prop("checked", !!LETTRAGE.hide_settled);
}

// ── header buttons ───────────────────────────────────────────────────────────

function lettrage_setup_page_buttons(report) {
	report.page.set_primary_action(__("Lettrage automatique"), () => lettrage_run_auto("lettrage"));
	report.page.add_inner_button(__("Delettrage automatique"), () => {
		frappe.confirm(__("Delettrer tous les groupes automatiques de la selection ?"), () =>
			lettrage_run_auto("delettrage")
		);
	});
	report.page.add_inner_button(__("Suggerer"), () => lettrage_show_suggestions());
	report.page.add_inner_button(__("Filtres"), () => {
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
			frappe.show_alert({
				message: __(kind === "lettrage" ? "Lettrage automatique lance." : "Delettrage automatique lance."),
				indicator: "blue",
			});
		},
	});
}

// ── column visibility (Affichage) ────────────────────────────────────────────

function lettrage_show_columns_dialog() {
	const labels = {
		mvt: __("Mvt"),
		journal: __("Jrn"),
		ref_doc: __("N° Piece"),
		libelle: __("Libelle"),
		lettrage: __("Lettre"),
		pointe: __("Pointe"),
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

// ── realtime progress ────────────────────────────────────────────────────────

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
		return `<button class="btn btn-xs ${LETTRAGE.category === cat ? "btn-primary" : "btn-default"}" data-cat="${lettrage_esc(cat)}">${label}</button>`;
	}).join("");
	const $tabs = LETTRAGE.$layout.find("#lettrage-cats");
	$tabs.html(html);
	$tabs.find("button")
		.off("click")
		.on("click", (e) => {
			LETTRAGE.category = $(e.currentTarget).data("cat");
			lettrage_set_hidden_filter("category", LETTRAGE.category);
			LETTRAGE.account = "";
			lettrage_set_hidden_filter("account", "");
			LETTRAGE.selection = {};
			lettrage_render_tabs();
			lettrage_render_account_head();
			lettrage_render_selection_bar();
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
					${lettrage_side_chip(account.solde)}
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
			LETTRAGE.account = LETTRAGE.account === name ? "" : name;
			lettrage_set_hidden_filter("account", LETTRAGE.account);
			LETTRAGE.selection = {};
			LETTRAGE_PAGINATION.reset_page();
			lettrage_render_accounts(LETTRAGE.accounts);
			lettrage_render_account_head();
			lettrage_render_selection_bar();
			frappe.query_report.refresh();
		});
}

// ── account head + tabs ──────────────────────────────────────────────────────

function lettrage_render_account_head() {
	const $head = LETTRAGE.$layout.find("#lettrage-account-head");
	if (!LETTRAGE.account) {
		$head.html(`<div class="text-muted">${__("Pick an account on the left.")}</div>`);
		return;
	}
	const meta = (LETTRAGE.accounts || []).find((a) => a.account === LETTRAGE.account);
	const name = meta ? meta.name : String(LETTRAGE.account).split(" - ")[0];
	const solde = meta ? lettrage_side_chip(meta.solde) : "";
	$head.html(
		`<b style="font-size:13px;">${lettrage_esc(name)}</b>
		<span class="lettrage-jrn-chip">${lettrage_esc(LETTRAGE.account)}</span>
		${solde}`
	);
}

function lettrage_render_tabs() {
	const $tabs = LETTRAGE.$layout.find("#lettrage-line-tabs");
	$tabs.html(
		LETTRAGE_TABS.map(
			(tab) =>
				`<button class="btn btn-xs ${LETTRAGE.tab === tab ? "btn-primary" : "btn-default"}" data-tab="${lettrage_esc(tab)}">${__(tab)}</button>`
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
			lettrage_render_selection_bar();
			frappe.query_report.refresh();
		});
}

// ── selection: group-linked, cross-page ──────────────────────────────────────

function lettrage_checked_indices() {
	const datatable = frappe.query_report.datatable;
	if (!datatable || !datatable.rowmanager) return new Set();
	return new Set(datatable.rowmanager.getCheckedRows().map(Number));
}

function lettrage_sync_selection() {
	const checked = lettrage_checked_indices();
	const page_rows = frappe.query_report.data || [];
	const previously_selected = new Set(Object.keys(LETTRAGE.selection));

	page_rows.forEach((row, index) => {
		if (!row || !row.name) return;
		const is_checked = checked.has(index);
		const was_selected = previously_selected.has(row.name);
		if (is_checked === was_selected) return;

		if (is_checked) {
			LETTRAGE.selection[row.name] = row;
			// linked selection: a lettered line pulls its whole group in
			if (row.lettrage_groupe) {
				page_rows.forEach((other) => {
					if (other && other.lettrage_groupe === row.lettrage_groupe && other.name) {
						LETTRAGE.selection[other.name] = other;
					}
				});
			}
		} else {
			delete LETTRAGE.selection[row.name];
			if (row.lettrage_groupe) {
				page_rows.forEach((other) => {
					if (other && other.lettrage_groupe === row.lettrage_groupe && other.name) {
						delete LETTRAGE.selection[other.name];
					}
				});
			}
		}
	});

	lettrage_reapply_checks();
	lettrage_render_selection_bar();
}

function lettrage_reapply_checks() {
	const datatable = frappe.query_report.datatable;
	if (!datatable || !datatable.rowmanager || !LETTRAGE) return;
	LETTRAGE.syncing = true;
	try {
		datatable.rowmanager.checkAll(false);
		(frappe.query_report.data || []).forEach((row, index) => {
			if (row && row.name && LETTRAGE.selection[row.name]) {
				datatable.rowmanager.checkRow(index, true);
			}
		});
	} finally {
		LETTRAGE.syncing = false;
	}
}

function lettrage_selection_totals() {
	const names = Object.keys(LETTRAGE.selection);
	let debit = 0;
	let credit = 0;
	let lettered = 0;
	let locked = 0;
	names.forEach((name) => {
		const row = LETTRAGE.selection[name];
		debit += flt(row.debit);
		credit += flt(row.credit);
		if (row.lettrage_groupe) lettered += 1;
		if (row.declaration_cloture) locked += 1;
	});
	return {
		names,
		debit: flt(debit, 3),
		credit: flt(credit, 3),
		ecart: flt(debit - credit, 3),
		lettered,
		locked,
	};
}

// ── the sticky action bar ────────────────────────────────────────────────────

function lettrage_render_selection_bar() {
	const $bar = LETTRAGE.$layout.find("#lettrage-selection-bar");
	const { names, debit, credit, ecart, lettered, locked } = lettrage_selection_totals();
	if (!names.length) {
		$bar.empty();
		return;
	}
	const balanced = Math.abs(ecart) <= LETTRAGE_TOLERANCE;
	// the server requires at least two lines per lettering call (a one-line
	// partial-group join cannot happen: selecting a group line pulls the
	// whole group in)
	const enough = names.length >= 2;
	const lock_note = locked ? ` · <span class="text-danger">${__(" {0} ligne(s) verrouillee(s) (declaration cloturee)", [locked])}</span>` : "";
	$bar.html(
		`<div class="lettrage-actions-bar">
			<b>${__("Selection ({0})", [names.length])}</b>
			<span>${__("Debit {0}", [lettrage_fmt(debit)])} · ${__("Credit {0}", [lettrage_fmt(credit)])} ·
				Ecart <b class="${balanced ? "text-success" : "text-danger"}">${lettrage_fmt(ecart)}</b>${lock_note}</span>
			<button class="btn btn-primary btn-sm tu-letter"${balanced && enough ? "" : " disabled"}>${__("Lettrer")}</button>
			<button class="btn btn-sm btn-default tu-partiel"${!balanced && enough ? "" : " disabled"}>${__("Partiel")}</button>
			<button class="btn btn-sm btn-default tu-unletter"${lettered ? "" : " disabled"}>${__("Delettrer")}</button>
			<button class="btn btn-sm btn-default tu-suggest"${LETTRAGE.account ? "" : " disabled"}>${__("Suggerer")}</button>
			<button class="btn btn-sm btn-default tu-auto">${__("Auto")}</button>
		</div>`
	);
	$bar.find(".tu-letter").on("click", () => lettrage_letter_selection(names, 0));
	$bar.find(".tu-partiel").on("click", () => {
		frappe.confirm(
			__("Lettrage partiel ? L'ecart de {0} restera en Partiel.", [lettrage_fmt(ecart)]),
			() => lettrage_letter_selection(names, 1)
		);
	});
	$bar.find(".tu-unletter").on("click", () => {
		// locked rows (declaration_cloture) are filtered out: the server
		// rejects them anyway, and the accountant sees the lock chips
		const unlocked = names.filter((name) => !LETTRAGE.selection[name].declaration_cloture);
		if (!unlocked.length) {
			frappe.msgprint({
				message: __("Toutes les lignes selectionnees sont verrouillees par une declaration cloturee."),
				indicator: "orange",
			});
			return;
		}
		frappe.call({
			method: LETTRAGE_API + "unletter",
			args: { names: JSON.stringify(unlocked) },
			callback() {
				LETTRAGE.selection = {};
				lettrage_refresh_all();
			},
		});
	});
	$bar.find(".tu-suggest").on("click", () => lettrage_show_suggestions());
	$bar.find(".tu-auto").on("click", () => lettrage_run_auto("lettrage"));
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

function lettrage_refresh_all() {
	lettrage_load_accounts();
	frappe.query_report.refresh();
}

// ── pointage ─────────────────────────────────────────────────────────────────

function lettrage_bind_pointe(report) {
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
	if (!LETTRAGE.account) {
		frappe.msgprint({ message: __("Choisissez un compte sur la gauche."), indicator: "orange" });
		return;
	}
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
