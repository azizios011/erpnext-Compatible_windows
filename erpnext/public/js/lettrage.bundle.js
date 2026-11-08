// Lettrage — the "Saisie du lettrage" tool UI (Axeane screen), rendered into
// the Lettrage form's ui_html field. Left panel: account cards by category.
// Right panel: line table with tabs, filters, selection lettering, pointage
// and the background auto-lettrage progress. Served as a hashed bundle.
(function () {
	"use strict";

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
	const CATEGORIES = ["Tous", "Clients", "Fournisseurs", "Salaries", "Debiteurs-Crediteurs", "Autres"];
	const TABS = ["Non lettrees", "Partielles", "Lettrees", "Toutes"];
	const PAGE_SIZES = [15, 25, 50, 100, 250];
	const METHOD = "erpnext.custom_modules.reports.doctype.lettrage.lettrage.";

	let state = null;
	let realtime_bound = false;

	function fmt(value) {
		return frappe.utils.format_number(flt(value), null, 3);
	}

	function esc(value) {
		return frappe.utils.escape_html(cstr(value));
	}

	function cstr(value) {
		return value === null || value === undefined ? "" : String(value);
	}

	erpnext.lettrage = { render };

	function render(frm) {
		const wrapper = frm.fields_dict.ui_html && frm.fields_dict.ui_html.$wrapper;
		if (!wrapper) {
			return;
		}
		state = {
			frm,
			category: "Tous",
			search: "",
			hide_settled: 1,
			sort_by: "numero",
			account: null,
			tab: "Non lettrees",
			page: 1,
			page_size: 25,
			filters: {},
			selection: {},
			columns: {
				mvt: 1,
				jrn: 1,
				ref: 1,
				libelle: 1,
				tresorerie: 0,
				lettre: 1,
				pointe: 1,
			},
		};
		wrapper.html(shell_html());
		bind_shell(wrapper);
		bind_realtime();
		bind_context_changes(wrapper);
		load_accounts();
	}

	/** Every query is scoped server-side by the dock context: a context
	 * switch simply re-runs them. */
	function bind_context_changes(wrapper) {
		$(document)
			.off("axeane-context-changed.lettrage")
			.on("axeane-context-changed.lettrage", () => {
				if (!wrapper.is(":visible") || !$("#lettrage-lines-wrap").length) {
					return;
				}
				state.selection = {};
				load_accounts();
				load_lines();
			});
	}

	function shell_html() {
		return `
			<style>
				.lettrage-tool { display: flex; gap: 12px; align-items: stretch; min-height: 70vh; }
				.lettrage-left { width: 300px; min-width: 240px; border: 1px solid var(--border-color); border-radius: 8px; display: flex; flex-direction: column; max-height: 78vh; }
				.lettrage-left.collapsed { width: 44px; min-width: 44px; cursor: pointer; }
				.lettrage-left.collapsed .lettrage-left-body { display: none; }
				.lettrage-left-body { padding: 10px; overflow-y: auto; flex: 1; }
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
				.lettrage-right { flex: 1; display: flex; flex-direction: column; min-width: 0; }
				.lettrage-right-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; flex-wrap: wrap; }
				.lettrage-stats { display: flex; gap: 16px; }
				.lettrage-stat { text-align: right; }
				.lettrage-stat .stat-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; }
				.lettrage-stat .stat-value { font-size: 14px; font-weight: 700; }
				.lettrage-tabs { display: flex; gap: 4px; margin: 8px 0; }
				.lettrage-tabs button { font-size: 11px; padding: 2px 10px; border-radius: 12px; }
				.lettrage-tabs button.active { background: var(--brand-primary, #2490ef); color: #fff; }
				.lettrage-lines { width: 100%; border-collapse: collapse; font-size: 11.5px; }
				.lettrage-lines th { text-align: left; border-bottom: 1px solid var(--border-color); padding: 4px 6px; cursor: pointer; white-space: nowrap; }
				.lettrage-lines td { padding: 3px 6px; border-bottom: 1px solid var(--control-bg, #eee); }
				.lettrage-lines tr.selected td { background: var(--control-bg, #f3f7ff); }
				.lettrage-lines td.num, .lettrage-lines th.num { text-align: right; }
				.jrn-chip { background: var(--bg-blue, #e2eaff); border-radius: 8px; padding: 0 6px; font-size: 10px; font-weight: 600; }
				.side-chip { border-radius: 8px; padding: 0 5px; font-size: 10px; font-weight: 700; }
				.side-chip.D { background: #e6f4ea; color: #1a7f37; }
				.side-chip.C { background: #fdecec; color: #c0392b; }
				.lettrage-actions-bar { position: sticky; bottom: 0; background: var(--card-bg, #fff); border: 1px solid var(--border-color); border-radius: 6px; padding: 6px 10px; display: flex; gap: 10px; align-items: center; z-index: 4; }
				.lettrage-progress { margin-top: 6px; }
				.lettrage-footer { display: flex; gap: 8px; align-items: center; margin-top: 6px; font-size: 11px; color: var(--text-muted); }
			</style>
			<div class="lettrage-tool">
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
				<div class="lettrage-right">
					<div class="lettrage-right-head">
						<div id="lettrage-account-head"></div>
						<div class="lettrage-stats" id="lettrage-stats"></div>
					</div>
					<div id="lettrage-top-actions" style="margin: 6px 0;"></div>
					<div class="lettrage-progress" id="lettrage-progress"></div>
					<div class="lettrage-tabs" id="lettrage-line-tabs"></div>
					<div id="lettrage-lines-wrap"></div>
					<div class="lettrage-footer" id="lettrage-right-footer"></div>
					<div id="lettrage-selection-bar"></div>
				</div>
			</div>
		`;
	}

	function bind_shell(wrapper) {
		wrapper.find("#lettrage-left").on("click", (e) => {
			if ($(e.target).closest("input, button, .lettrage-account-card").length) return;
			wrapper.find("#lettrage-left").toggleClass("collapsed");
		});
		wrapper.find("#lettrage-search").on(
			"input",
			frappe.utils.debounce(() => {
				state.search = wrapper.find("#lettrage-search").val();
				load_accounts();
			}, 300)
		);
		wrapper.find("#lettrage-hide-settled").on("change", (e) => {
			state.hide_settled = e.target.checked ? 1 : 0;
			load_accounts();
		});
		wrapper.find(".tu-sort").on("click", (e) => {
			state.sort_by = $(e.currentTarget).data("sort");
			load_accounts();
		});
	}

	function bind_realtime() {
		if (realtime_bound) return;
		realtime_bound = true;
		frappe.realtime.on("lettrage_progress", (data) => {
			const $progress = $("#lettrage-progress");
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
				if (state.account) load_lines();
				load_accounts();
			}
		});
	}

	function load_accounts() {
		frappe.call({
			method: METHOD + "get_accounts",
			args: {
				category: state.category,
				search: state.search || "",
				hide_settled: state.hide_settled,
				sort_by: state.sort_by,
			},
			callback(r) {
				const message = r.message || { accounts: [], totals: {} };
				render_categories();
				render_overview(message.totals || {});
				render_accounts(message.accounts || []);
			},
		});
	}

	function render_categories() {
		const html = CATEGORIES.map((cat) => {
			const label = cat === "Debiteurs-Crediteurs" ? __("Debiteurs-Crediteurs") : __(cat);
			return `<button class="btn btn-xs btn-default ${state.category === cat ? "active" : ""}" data-cat="${esc(cat)}">${label}</button>`;
		}).join("");
		$("#lettrage-cats").html(html);
		$("#lettrage-cats button")
			.off("click")
			.on("click", (e) => {
				state.category = $(e.currentTarget).data("cat");
				state.account = null;
				load_accounts();
				load_lines();
			});
	}

	function render_overview(totals) {
		$("#lettrage-overview").html(
			`<b>${__("Vue d'ensemble")}</b><br>
			${__("{0} compte(s)", [totals.account_count || 0])} ·
			${__("total {0} a lettrer", [totals.total_a_lettrer || 0])}
			${totals.hidden_settled ? ` · ${__("{0} solde(s) masque(s)", [totals.hidden_settled])}` : ""}`
		);
		$("#lettrage-left-footer").html(
			`${__(" {0} compte(s)", [totals.account_count || 0])} · ${__(" {0} solde(s) masque(s)", [
				totals.hidden_settled || 0,
			])}`
		);
	}

	function render_accounts(accounts) {
		const $wrap = $("#lettrage-accounts");
		if (!accounts.length) {
			$wrap.html(`<div class="text-muted" style="padding:8px 0;">${__("No account to letter.")}</div>`);
			return;
		}
		$wrap.html(
			accounts
				.map(
					(account) => `
				<div class="lettrage-account-card ${state.account === account.account ? "active" : ""}" data-account="${esc(account.account)}">
					<div style="display:flex; justify-content:space-between; gap:6px;">
						<span class="acc-num">${esc(account.number)}</span>
						<span class="acc-num">${fmt(account.solde)} ${account.side}</span>
					</div>
					<div style="display:flex; justify-content:space-between; gap:6px;">
						<span class="acc-name">${esc(account.name)}</span>
						${account.a_lettrer ? `<span class="lettrage-chip">${__(" {0} a lettrer", [account.a_lettrer])}</span>` : ""}
					</div>
				</div>`
				)
				.join("")
		);
		$wrap.find(".lettrage-account-card")
			.off("click")
			.on("click", (e) => {
				state.account = $(e.currentTarget).data("account");
				state.page = 1;
				load_accounts();
				load_lines();
			});
	}

	function load_lines() {
		const $head = $("#lettrage-account-head");
		if (!state.account) {
			$head.html(`<div class="text-muted" style="padding: 20px 0;">${__("Pick an account on the left.")}</div>`);
			$("#lettrage-stats").empty();
			$("#lettrage-line-tabs").empty();
			$("#lettrage-lines-wrap").empty();
			$("#lettrage-right-footer").empty();
			$("#lettrage-selection-bar").empty();
			$("#lettrage-top-actions").empty();
			return;
		}
		frappe.call({
			method: METHOD + "get_lines",
			args: {
				account: state.account,
				tab: state.tab,
				filters: JSON.stringify(state.filters),
				page: state.page,
				page_size: state.page_size,
			},
			callback(r) {
				const message = r.message || { rows: [], stats: {}, total: 0 };
				state.total = message.total || 0;
				render_account_head(message.stats || {});
				render_tabs();
				render_top_actions();
				render_lines(message.rows || []);
				render_footer(message);
				render_selection_bar();
			},
		});
	}

	function account_info() {
		return state.account_info || {};
	}

	function render_account_head(stats) {
		const name = state.account ? state.account.split(" - ")[0] : "";
		$("#lettrage-account-head").html(
			`<b style="font-size:13px;">${esc(name)}</b>
			<span class="jrn-chip">${esc(state.account || "")}</span>`
		);
		$("#lettrage-stats").html(
			`<div class="lettrage-stat"><div class="stat-label">${__("SOLDE")}</div>
				<div class="stat-value">${fmt(stats.solde || 0)}</div></div>
			<div class="lettrage-stat"><div class="stat-label">${__("NON LETTRE")}</div>
				<div class="stat-value">${stats.non_lettre || 0}</div></div>
			<div class="lettrage-stat"><div class="stat-label">${__("LIGNES A LETTRER")}</div>
				<div class="stat-value">${stats.lignes_a_lettrer || 0}</div></div>`
		);
	}

	function render_tabs() {
		$("#lettrage-line-tabs").html(
			TABS.map(
				(tab) =>
					`<button class="btn btn-xs btn-default ${state.tab === tab ? "active" : ""}" data-tab="${esc(tab)}">${__(tab)}</button>`
			).join("")
		);
		$("#lettrage-line-tabs button")
			.off("click")
			.on("click", (e) => {
				state.tab = $(e.currentTarget).data("tab");
				state.page = 1;
				load_lines();
			});
	}

	function render_top_actions() {
		$("#lettrage-top-actions").html(
			`<button class="btn btn-primary btn-sm tu-auto">${__("Lettrage automatique")}</button>
			<button class="btn btn-sm tu-auto-del" style="border:1px solid var(--text-on-red, #c0392b); color: var(--text-on-red, #c0392b);">${__(
				"Delettrage automatique"
			)}</button>
			<button class="btn btn-default btn-sm tu-suggest">${__("Suggerer")}</button>
			<button class="btn btn-default btn-sm tu-filters">${__("Filtres")}</button>
			<button class="btn btn-default btn-sm tu-cols">${__("Affichage")}</button>
			<button class="btn btn-default btn-sm tu-refresh">${__("Refresh")}</button>`
		);
		$("#lettrage-top-actions .tu-auto").on("click", () => run_auto("lettrage"));
		$("#lettrage-top-actions .tu-auto-del").on("click", () => {
			frappe.confirm(__("Delettrer tous les groupes automatiques de la selection ?"), () =>
				run_auto("delettrage")
			);
		});
		$("#lettrage-top-actions .tu-suggest").on("click", show_suggestions);
		$("#lettrage-top-actions .tu-filters").on("click", show_filters_dialog);
		$("#lettrage-top-actions .tu-cols").on("click", show_columns_dialog);
		$("#lettrage-top-actions .tu-refresh").on("click", () => load_lines());
	}

	function run_auto(kind) {
		frappe.call({
			method: METHOD + (kind === "lettrage" ? "run_auto_lettrage" : "run_auto_delettrage"),
			args: {
				category: state.category,
				account: state.account || "ALL",
				rules: JSON.stringify(["R1", "R2"]),
			},
			callback() {
				frappe.show_alert({ message: __("Lettrage automatique lance."), indicator: "blue" });
			},
		});
	}

	function show_suggestions() {
		if (!state.account) return;
		frappe.call({
			method: METHOD + "suggest",
			args: { account: state.account },
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
								.map((c, i) => `${i}:${c.rule} ${c.key} (${c.count} ${__("lignes")}, ${fmt(c.total_debit)})`)
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
							method: METHOD + "letter_lines",
							args: {
								account: state.account,
								names: JSON.stringify(candidate.names),
								allow_partial: 0,
							},
							callback() {
								frappe.show_alert({ message: __("Lettrer OK."), indicator: "green" });
								load_lines();
								load_accounts();
							},
						});
					},
				});
				d.show();
			},
		});
	}

	function show_filters_dialog() {
		const d = new frappe.ui.Dialog({
			title: __("Filtres"),
			fields: [
				{ fieldname: "from_date", fieldtype: "Date", label: __("Du") },
				{ fieldname: "to_date", fieldtype: "Date", label: __("Au") },
				{ fieldname: "journal", fieldtype: "Link", options: "Journal", label: __("Journal") },
				{ fieldname: "amount_min", fieldtype: "Float", label: __("Montant min") },
				{ fieldname: "amount_max", fieldtype: "Float", label: __("Montant max") },
				{ fieldname: "libelle", fieldtype: "Data", label: __("Libelle contient") },
			],
			primary_action_label: __("Afficher"),
			primary_action(values) {
				d.hide();
				state.filters = values || {};
				state.page = 1;
				load_lines();
			},
			secondary_action_label: __("Reinitialiser"),
			secondary_action() {
				d.hide();
				state.filters = {};
				state.page = 1;
				load_lines();
			},
		});
		d.set_values(state.filters || {});
		d.show();
	}

	function show_columns_dialog() {
		const labels = {
			mvt: __("MVT"),
			jrn: __("JRN"),
			ref: __("N° PIECE"),
			libelle: __("LIBELLE"),
			tresorerie: __("Tresorerie"),
			lettre: __("LETTRE"),
			pointe: __("POINTE"),
		};
		const d = new frappe.ui.Dialog({
			title: __("Affichage"),
			fields: Object.keys(labels).map((fieldname) => ({
				fieldname: fieldname,
				fieldtype: "Check",
				label: labels[fieldname],
				default: state.columns[fieldname] ? 1 : 0,
			})),
			primary_action_label: __("OK"),
			primary_action(values) {
				d.hide();
				Object.assign(state.columns, values || {});
				load_lines();
			},
		});
		d.show();
	}

	function columns_visible() {
		return state.columns;
	}

	function render_lines(rows) {
		const cols = columns_visible();
		const $wrap = $("#lettrage-lines-wrap");
		if (!state.account) {
			$wrap.empty();
			return;
		}
		const th = (label, key, num) =>
			`<th class="${num ? "num" : ""}" data-sort="${esc(key || "")}">${esc(label)}</th>`;
		const head =
			`<th style="width:22px;"><input type="checkbox" id="lettrage-check-all"></th>` +
			`<th>${__("DATE")}</th>` +
			(cols.mvt ? th("MVT", "mvt") : "") +
			(cols.jrn ? th("JRN", "journal") : "") +
			(cols.ref ? th("N° PIECE", "ref_doc") : "") +
			(cols.libelle ? th("LIBELLE", "libelle") : "") +
			`<th class="num">${__("DEBIT")}</th><th class="num">${__("CREDIT")}</th>` +
			`<th class="num">${__("SOLDE PROG.")}</th>` +
			(cols.lettre ? th("LETTRE", "lettrage") : "") +
			(cols.pointe ? th("POINTE", "pointe") : "");

		const body = rows
			.map((row) => {
				const checked = state.selection[row.name] ? "checked" : "";
				const cells =
					`<td><input type="checkbox" class="tu-line-check" data-name="${esc(row.name)}" ${checked}></td>` +
					`<td>${esc(row.date)}</td>` +
					(cols.mvt
						? `<td>${row.mvt ? `<a href="/app/form/Ecriture Comptable/${esc(row.name)}">${esc(row.mvt)}</a>` : ""}</td>`
						: "") +
					(cols.jrn ? `<td>${row.jrn ? `<span class="jrn-chip">${esc(row.jrn)}</span>` : ""}</td>` : "") +
					(cols.ref ? `<td>${esc(row.ref_doc)}</td>` : "") +
					(cols.libelle ? `<td>${esc(row.libelle)}</td>` : "") +
					`<td class="num">${row.debit ? fmt(row.debit) : ""}</td>` +
					`<td class="num">${row.credit ? fmt(row.credit) : ""}</td>` +
					`<td class="num">${fmt(row.solde_prog)} <span class="side-chip ${row.side}">${row.side}</span></td>` +
					(cols.lettre
						? `<td>${esc(row.lettrage)}${row.lettrage_status === "Partiel" ? " (" + __("Partiel") + ")" : ""}</td>`
						: "") +
					(cols.pointe
						? `<td style="text-align:center;"><input type="checkbox" class="tu-pointe" data-name="${esc(
								row.name
							)}" data-value="${row.pointe ? 0 : 1}" ${row.pointe ? "checked" : ""}></td>`
						: "");
				return `<tr data-name="${esc(row.name)}" class="${state.selection[row.name] ? "selected" : ""}">${cells}</tr>`;
			})
			.join("");

		$wrap.html(
			`<table class="lettrage-lines"><thead><tr>${head}</tr></thead><tbody>${body || ""}</tbody></table>` +
				(rows.length
					? ""
					: `<div class="text-muted" style="padding: 12px 0;">${__("No line for these filters.")}</div>`)
		);

		bind_line_events($wrap, rows);
		render_footer({ total: state.total, page: state.page, page_size: state.page_size });
	}

	function bind_line_events($wrap, rows) {
		$wrap.find("#lettrage-check-all").on("change", (e) => {
			const checked = e.target.checked;
			rows.forEach((row) => {
				state.selection[row.name] = checked ? row : undefined;
				delete state.selection[row.name];
				if (checked) state.selection[row.name] = row;
			});
			$wrap.find(".tu-line-check").prop("checked", checked);
			$wrap.find("tr").toggleClass("selected", checked);
			render_selection_bar();
		});
		$wrap.find(".tu-line-check").on("change", (e) => {
			const $check = $(e.currentTarget);
			const name = $check.data("name");
			const row = rows.find((r) => r.name === name);
			if ($check.is(":checked")) {
				if (row) state.selection[name] = row;
			} else {
				delete state.selection[name];
			}
			$check.closest("tr").toggleClass("selected", $check.is(":checked"));
			render_selection_bar();
		});
		$wrap.find(".tu-pointe").on("change", (e) => {
			const $check = $(e.currentTarget);
			frappe.call({
				method: METHOD + "toggle_pointe",
				args: { names: JSON.stringify([$check.data("name")]), value: $check.data("value") },
				callback() {
					load_lines();
				},
			});
		});
		$wrap.find("th[data-sort]").on("click", (e) => {
			const sort_field = $(e.currentTarget).data("sort");
			state.filters = state.filters || {};
			if (state.filters.order_by === sort_field) {
				delete state.filters.order_by;
			} else {
				state.filters.order_by = sort_field;
			}
			load_lines();
		});
	}

	function selection_totals() {
		const names = Object.keys(state.selection);
		let debit = 0;
		let credit = 0;
		names.forEach((name) => {
			debit += flt(state.selection[name].debit);
			credit += flt(state.selection[name].credit);
		});
		return { names, debit: flt(debit, 3), credit: flt(credit, 3), ecart: flt(debit - credit, 3) };
	}

	function render_selection_bar() {
		const $bar = $("#lettrage-selection-bar");
		const { names, debit, credit, ecart } = selection_totals();
		if (!names.length) {
			$bar.empty();
			return;
		}
		$bar.html(
			`<div class="lettrage-actions-bar">
				<b>${__("Lettrer ({0})", [names.length])}</b>
				<span>${__("Debit {0}", [fmt(debit)])} · ${__("Credit {0}", [fmt(credit)])} ·
					Ecart <b class="${ecart ? "text-danger" : "text-success"}">${fmt(ecart)}</b></span>
				<button class="btn btn-primary btn-sm tu-letter">${__("Lettrer")}</button>
				<button class="btn btn-sm tu-unletter" style="border:1px solid var(--text-on-red, #c0392b); color: var(--text-on-red, #c0392b);">${__(
					"Delettrer"
				)}</button>
			</div>`
		);
		$bar.find(".tu-letter").on("click", () => {
			const allow_partial = Math.abs(ecart) > 0.001 ? 1 : 0;
			if (allow_partial) {
				frappe.confirm(
					__("Lettrage partiel ? L'ecart de {0} restera en Partiel.", [fmt(ecart)]),
					() => letter_selection(names, allow_partial)
				);
			} else {
				letter_selection(names, 0);
			}
		});
		$bar.find(".tu-unletter").on("click", () => {
			frappe.call({
				method: METHOD + "unletter",
				args: { names: JSON.stringify(names) },
				callback() {
					state.selection = {};
					load_lines();
					load_accounts();
				},
			});
		});
	}

	function letter_selection(names, allow_partial) {
		frappe.call({
			method: METHOD + "letter_lines",
			args: {
				account: state.account,
				names: JSON.stringify(names),
				allow_partial: allow_partial,
			},
			callback(r) {
				const message = r.message || {};
				state.selection = {};
				frappe.show_alert({
					message: __("Lettre {0}: {1} ligne(s), ecart {2}.", [message.code, message.count, fmt(message.ecart)]),
					indicator: message.status === "Lettre" ? "green" : "orange",
				});
				load_lines();
				load_accounts();
			},
		});
	}

	function render_footer(message) {
		const page_size_options = PAGE_SIZES.map(
			(size) =>
				`<button class="btn btn-xs btn-default tu-page-size ${state.page_size === size ? "active" : ""}" data-size="${size}">${size}</button>`
		).join("");
		const total_pages = Math.max(Math.ceil((message.total || 0) / (message.page_size || state.page_size)), 1);
		$("#lettrage-right-footer").html(
			`<span>${__(" {0} lignes", [message.total || 0])}</span>
			<span>${page_size_options}</span>
			<button class="btn btn-xs btn-default tu-page-prev" ${state.page <= 1 ? "disabled" : ""}>&larr;</button>
			<span>${__("Page {0} of {1}", [message.page || 1, total_pages])}</span>
			<button class="btn btn-xs btn-default tu-page-next" ${state.page >= total_pages ? "disabled" : ""}>&rarr;</button>`
		);
		$("#lettrage-right-footer .tu-page-size")
			.off("click")
			.on("click", (e) => {
				state.page_size = $(e.currentTarget).data("size");
				state.page = 1;
				load_lines();
			});
		$("#lettrage-right-footer .tu-page-prev")
			.off("click")
			.on("click", () => {
				if (state.page > 1) {
					state.page -= 1;
					load_lines();
				}
			});
		$("#lettrage-right-footer .tu-page-next")
			.off("click")
			.on("click", () => {
				state.page += 1;
				load_lines();
			});
	}
})();
