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

// ── Grand Livre document views (XLSX / PDF) ──────────────────────────────────
// Both views render the SAME generated document: the PDF is always converted
// from the xlsx (print_designer.api.ledger_documents). The xlsx view embeds
// the bundled GenOffice Sheets editor (print_designer/editors/sheets) over
// the same iframe + postMessage handshake the /app/sheets-editor desk page
// uses, with readonly: true — posted ledger data must not be editable and the
// adapter refuses saves anyway. The pdf view uses the browser's viewer on the
// private File url. Filters stay in the report's filter section: every
// (re)mount regenerates the document for the CURRENT filter values.

const GL_DOCS = {
	generate_xlsx: "print_designer.api.ledger_documents.generate_grand_livre_xlsx",
	generate_pdf: "print_designer.api.ledger_documents.generate_grand_livre_pdf",
};

const GL_VIEW_STATE = { active: "list", el: null, timer: null, generation: 0 };

// ── List view pagination (server-side paging, client state) ─────────────────
// The page number and the FIXED page size live in two HIDDEN filters: they
// stay part of the report's filter set so get_filter_values() sends them to
// the server on every run, while the filter bar shows nothing of them. Any
// real filter change resets to page 1 (on_change on every visible filter);
// the refresh button keeps the current page because it never touches these
// values. The server message ("Showing X - Y of N rows (page P of M).") is
// the only channel that carries the paging numbers — show_report_message is
// intercepted below: the numbers feed the bottom bar and the native
// form-message above the table never shows (no duplicate text).

const GL_PAGE_SIZE = 500;

const GL_PAGINATION = {
	state: { page: 1, pages: 1, total: 0, start: 0, end: 0 },

	// read the 5 integers positionally from the server message: the wording
	// may be translated, the number order is not
	update_from_message(message) {
		const numbers = (message || "").match(/\d+/g) || [];
		if (numbers.length !== 5) return false;
		const [start, end, total, page, pages] = numbers.map(Number);
		this.state = { start, end, total, page, pages: Math.max(pages, 1) };
		return true;
	},

	set_hidden_filter(fieldname, value) {
		// hidden filters have no visible input: get_filter_values() reads
		// f.value for them, so write the value straight on the control
		const field = frappe.query_report.get_filter(fieldname, false);
		if (field) field.value = value;
	},

	reset_page() {
		this.set_hidden_filter("page", 1);
		this.state.page = 1;
	},

	goto(page) {
		const pages = this.state.pages || 1;
		const target = Math.max(1, Math.min(Math.floor(page) || 1, pages));
		this.set_hidden_filter("page", target);
		this.state.page = target;
		frappe.query_report.refresh();
	},

	page_buttons(current, pages) {
		// up to 5 page numbers around the current page, "…" outside the window
		const window_start = Math.max(1, Math.min(current - 2, pages - 4));
		const window_end = Math.min(pages, window_start + 4);
		const out = [];
		if (window_start > 1) out.push(1, "…");
		for (let p = window_start; p <= window_end; p++) out.push(p);
		if (window_end < pages) out.push("…", pages);
		return out;
	},

	render($area) {
		if (!$area || !$area.length) return;
		const { page, pages, start, end, total } = this.state;
		if (!total) {
			$area.empty();
			return;
		}
		const button = (attrs, label, disabled, primary) =>
			`<button type="button" class="btn btn-xs ${primary ? "btn-primary" : "btn-default"}"${
				disabled ? " disabled" : ""
			}${attrs}>${__(label)}</button>`;
		const buttons = [];
		buttons.push(button(' data-gl-page="first"', __("Premier"), page <= 1));
		buttons.push(button(' data-gl-page="prev"', __("Précédent"), page <= 1));
		this.page_buttons(page, pages).forEach((item) => {
			if (item === "…") {
				buttons.push(`<button type="button" class="btn btn-xs btn-default" disabled>…</button>`);
			} else {
				buttons.push(button(` data-gl-page="${item}"`, String(item), false, item === page));
			}
		});
		buttons.push(button(' data-gl-page="next"', __("Suivant"), page >= pages));
		buttons.push(button(' data-gl-page="last"', __("Dernier"), page >= pages));
		$area.html(
			`<div class="btn-group gl-pages" role="group">${buttons.join("")}</div>` +
				`<span class="text-muted gl-showing">${__("Showing {0} - {1} of {2} rows", [
					start,
					end,
					total,
				])}</span>`
		);
	},
};

// any real filter change restarts the pagination at page 1 (df.on_change
// replaces frappe's default auto-refresh; the values-compare upstream keeps
// no-op changes from firing)
function gl_filter_changed(report) {
	GL_PAGINATION.reset_page();
	report.refresh(true);
}

function gl_view_toolbar(kind, status_html) {
	const esc = frappe.utils.escape_html;
	return `
		<div class="gl-doc-toolbar" style="
			display: flex; align-items: center; gap: 8px;
			padding: 8px 10px; border-bottom: 1px solid var(--border-color, #d1d8dd);
			background: var(--bg-color, #fff);
		">
			<button class="btn btn-xs btn-default gl-doc-download" data-kind="${kind}">
				${__("Telecharger")} ${kind === "xlsx" ? ".xlsx" : ".pdf"}
			</button>
			<span class="gl-doc-status text-muted" style="font-size: 12px;">${esc(status_html)}</span>
		</div>`;
}

function gl_download_document(kind) {
	const method = kind === "xlsx" ? GL_DOCS.generate_xlsx : GL_DOCS.generate_pdf;
	const filters = JSON.stringify(frappe.query_report.get_filter_values() || {});
	frappe.call({
		method,
		args: { filters },
		freeze: true,
		freeze_message: __("Generation du document..."),
		callback(r) {
			const result = r.message || {};
			if (!result.file_url) return;
			const anchor = document.createElement("a");
			anchor.href = result.file_url + (result.file_url.includes("?") ? "&" : "?") + "v=" + Date.now();
			anchor.download = result.name || "grand-livre." + kind;
			document.body.appendChild(anchor);
			anchor.click();
			anchor.remove();
		},
	});
}

function gl_mount_error(el, message) {
	const area = el.querySelector(".gl-doc-frame-area");
	if (area) {
		area.innerHTML = `<div class="gl-doc-loading text-muted" style="
			position: absolute; inset: 0; display: flex;
			align-items: center; justify-content: center; text-align: center; padding: 20px;
		">${frappe.utils.escape_html(message)}</div>`;
	}
}

function gl_mount_sheets_editor(area, file_docname) {
	const iframe = document.createElement("iframe");
	iframe.title = __("Grand Livre XLSX");
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
				readonly: true,
			},
			window.location.origin
		);
	};
	window.addEventListener("message", on_message);
	GL_VIEW_STATE.cleanup = () => window.removeEventListener("message", on_message);
	iframe.src = "/assets/print_designer/editors/sheets/index.html";
}

function gl_mount_pdf_viewer(area, file_url) {
	const iframe = document.createElement("iframe");
	iframe.title = __("Grand Livre PDF");
	iframe.style.cssText = "border: 0; width: 100%; height: 100%; display: block;";
	iframe.src = file_url + (file_url.includes("?") ? "&" : "?") + "v=" + Date.now();
	area.appendChild(iframe);
}

function gl_mount_document(el, kind) {
	// one generation at a time; stale callbacks never mount
	const generation = ++GL_VIEW_STATE.generation;
	GL_VIEW_STATE.active = kind;
	GL_VIEW_STATE.el = el;
	if (GL_VIEW_STATE.cleanup) {
		GL_VIEW_STATE.cleanup();
		GL_VIEW_STATE.cleanup = null;
	}
	el.innerHTML = `
		<div class="gl-doc-view" style="
			display: flex; flex-direction: column; width: 100%; height: 100%;
		">
			${gl_view_toolbar(kind, __("Generation en cours..."))}
			<div class="gl-doc-frame-area" style="flex: 1; position: relative; min-height: 0;">
				<div class="gl-doc-loading text-muted" style="
					position: absolute; inset: 0; display: flex;
					align-items: center; justify-content: center;
				">${__("Generation du Grand Livre...")}</div>
			</div>
		</div>`;
	el.querySelector(".gl-doc-download").addEventListener("click", () => gl_download_document(kind));

	frappe.call({
		method: kind === "xlsx" ? GL_DOCS.generate_xlsx : GL_DOCS.generate_pdf,
		args: { filters: JSON.stringify(frappe.query_report.get_filter_values() || {}) },
		callback(r) {
			if (generation !== GL_VIEW_STATE.generation || GL_VIEW_STATE.active !== kind) return;
			const result = r.message || {};
			if (!result.file_url) {
				gl_mount_error(el, __("La generation n'a rien produit"));
				frappe.show_alert({
					message: __("La generation n'a rien produit"),
					indicator: "red",
				});
				return;
			}
			const $status = el.querySelector(".gl-doc-status");
			if ($status) $status.textContent = __("Pages") + ": " + (result.pages || "?");
			const area = el.querySelector(".gl-doc-frame-area");
			area.innerHTML = "";
			if (kind === "xlsx") gl_mount_sheets_editor(area, result.file);
			else gl_mount_pdf_viewer(area, result.file_url);
		},
		error(r) {
			if (generation !== GL_VIEW_STATE.generation) return;
			const msg = (r && r.message) || __("La generation a echoue");
			gl_mount_error(el, msg);
			frappe.show_alert({
				message: msg,
				indicator: "red",
			});
		},
	});
}

function gl_unmount_document() {
	GL_VIEW_STATE.active = "list";
	if (GL_VIEW_STATE.el) {
		GL_VIEW_STATE.el.innerHTML = "";
		GL_VIEW_STATE.el = null;
	}
	GL_VIEW_STATE.generation += 1; // a stale callback never mounts
	if (GL_VIEW_STATE.cleanup) {
		GL_VIEW_STATE.cleanup();
		GL_VIEW_STATE.cleanup = null;
	}
	if (GL_VIEW_STATE.timer) {
		clearTimeout(GL_VIEW_STATE.timer);
		GL_VIEW_STATE.timer = null;
	}
}

function gl_remount_after_refresh() {
	// filters changed and the report refreshed: regenerate the document view
	// for the NEW filter values (debounced, loading state)
	if (GL_VIEW_STATE.active === "list" || !GL_VIEW_STATE.el) return;
	if (GL_VIEW_STATE.timer) clearTimeout(GL_VIEW_STATE.timer);
	GL_VIEW_STATE.timer = setTimeout(() => {
		GL_VIEW_STATE.timer = null;
		const el = GL_VIEW_STATE.el;
		const kind = GL_VIEW_STATE.active;
		if (el && kind !== "list") gl_mount_document(el, kind);
	}, 800);
}

const GL_DOCUMENT_VIEWS = {
	pdf: {
		mount(el) {
			gl_mount_document(el, "pdf");
		},
		unmount() {
			gl_unmount_document();
		},
	},
	xlsx: {
		mount(el) {
			gl_mount_document(el, "xlsx");
		},
		unmount() {
			gl_unmount_document();
		},
	},
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
			on_change: gl_filter_changed,
		},
		{
			fieldname: "journal",
			label: __("Code Journal"),
			fieldtype: "MultiSelectList",
			options: "Journal",
			get_data(txt) {
				return frappe.db.get_link_options("Journal", txt);
			},
			on_change: gl_filter_changed,
		},
		{
			fieldname: "period_type",
			label: __("Periode"),
			fieldtype: "Select",
			options: "Mensuelle\nTrimestrielle\nAnnuelle\nPersonnalisee",
			default: "Mensuelle",
			reqd: 1,
			on_change: gl_filter_changed,
		},
		{
			fieldname: "month",
			label: __("Mois"),
			fieldtype: "Select",
			options: "Janvier\nFevrier\nMars\nAvril\nMai\nJuin\nJuillet\nAout\nSeptembre\nOctobre\nNovembre\nDecembre",
			default: "Janvier",
			reqd: 1,
			depends_on: "eval:doc.period_type == 'Mensuelle'",
			on_change: gl_filter_changed,
		},
		{
			fieldname: "quarter",
			label: __("Trimestre"),
			fieldtype: "Select",
			options: "T1\nT2\nT3\nT4",
			default: "T1",
			depends_on: "eval:doc.period_type == 'Trimestrielle'",
			on_change: gl_filter_changed,
		},
		{
			fieldname: "from_date",
			label: __("Du"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
			on_change: gl_filter_changed,
		},
		{
			fieldname: "to_date",
			label: __("Au"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
			on_change: gl_filter_changed,
		},
		{
			fieldname: "devise",
			label: __("Devise"),
			fieldtype: "Link",
			options: "Currency",
			default: "TND",
			on_change: gl_filter_changed,
		},
		{
			fieldname: "lettrage",
			label: __("Lettrage"),
			fieldtype: "Select",
			options: "Tous\nLettre\nNon lettre",
			default: "Tous",
			on_change: gl_filter_changed,
		},
		{
			fieldname: "extract_type",
			label: __("Type Extrait"),
			fieldtype: "Select",
			options: "Tous les comptes\nComptes mouvementes\nComptes non soldes",
			default: "Tous les comptes",
			reqd: 1,
			on_change: gl_filter_changed,
		},
		// pagination lives in client state: the page number and the FIXED
		// page size are hidden filters — never shown in the bar, still sent
		// to the server with every run (see GL_PAGINATION above)
		{
			fieldname: "page_size",
			label: __("Lignes par page"),
			fieldtype: "Int",
			default: GL_PAGE_SIZE,
			hidden: 1,
		},
		{
			fieldname: "page",
			label: __("Page"),
			fieldtype: "Int",
			default: 1,
			hidden: 1,
		},
		{
			fieldname: "mvt",
			label: __("Piece comptable"),
			fieldtype: "Data",
			description: __("One or several MVT numbers, comma-separated"),
			on_change: gl_filter_changed,
		},
	],

	// the PDF / XLSX mounts the switcher calls: el = the wide-open container,
	// filters = the CURRENT filter values (report.get_filter_values()). The
	// real previews are built later on this contract.
	views: GL_DOCUMENT_VIEWS,


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
		return default_formatter(value, row, column, data);
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

		// the import button comes first: a failure in the optional view
		// switcher must never hide the required pieces
		setup_import_actions(report);

		// the view switcher (PDF / List / XLSX) and the bottom summary bar
		// are shared with the Balance report (report_views.bundle.js): the
		// summary moves below the datatable in list view, the pdf / xlsx
		// placeholders mount with the current filter values, and a dock
		// context change re-runs the query and re-mounts the active view.
		// Optional: a failure is logged and surfaced, the report stays
		try {
			erpnext.reports.setup_views(report, {
				report_name: "Ledger Data",
				views: GL_DOCUMENT_VIEWS,
				keep_filters: true,
				pagination: GL_PAGINATION,
			});
			GL_PAGINATION.$area = report.page.main.find(".report-pagination");
		} catch (error) {
			console.error("report_views: setup_views failed", error);
			frappe.show_alert({
				message: __("Les vues PDF / XLSX n'ont pas pu etre chargees"),
				indicator: "orange",
			});
		}

		// the list fills the screen: the page section becomes a flex column
		// (filters / datatable / bottom bar), the datatable lays its columns
		// out fluid across the full width and the scrollable body takes the
		// height the flex chain leaves it — see the report-gl-fill CSS in
		// report_views.bundle.js. Scoped to this report: Balance is untouched.
		report.page.main.addClass("report-gl-fill");
		report.report_settings.get_datatable_options = (options) =>
			Object.assign({}, options, { layout: "fluid" });

		// the server message feeds the bottom bar pagination and never shows
		// above the table (no duplicate text); the empty-run case shows no
		// message at all, so the bar simply clears
		report.show_report_message = (message) => {
			if (GL_PAGINATION.update_from_message(message)) {
				GL_PAGINATION.render(GL_PAGINATION.$area);
			}
			report.$report_message.hide();
		};

		// the pagination buttons go through one delegated handler (they are
		// re-rendered on every server message, the binding survives)
		report.page.main
			.off("click.gl-pagination", ".gl-pages button")
			.on("click.gl-pagination", ".gl-pages button", function (event) {
				event.preventDefault();
				if ($(this).hasClass("disabled") || this.disabled) return;
				const target = $(this).attr("data-gl-page");
				if (!target) return;
				const { page, pages } = GL_PAGINATION.state;
				if (target === "first") GL_PAGINATION.goto(1);
				else if (target === "prev") GL_PAGINATION.goto(page - 1);
				else if (target === "next") GL_PAGINATION.goto(page + 1);
				else if (target === "last") GL_PAGINATION.goto(pages);
				else GL_PAGINATION.goto(parseInt(target, 10));
			});

		// the document views regenerate on refresh: a filter change while the
		// PDF / XLSX view is active re-mounts it with the new filter values
		// (gl_remount_after_refresh debounces; the mount shows the loading
		// state). The list view keeps the native refresh below.
		const previous_after_render = report.report_settings.after_datatable_render;
		report.report_settings.after_datatable_render = () => {
			if (previous_after_render) previous_after_render();
			gl_remount_after_refresh();
		};

		// downloads are available in every view (menu items; the document
		// views also carry their own toolbar button)
		report.page.add_menu_item(__("Telecharger XLSX"), () => gl_download_document("xlsx"));
		report.page.add_menu_item(__("Telecharger PDF"), () => gl_download_document("pdf"));
	}
};

// ── Grand Livre xlsx import (Accounts Manager / System Manager) ──────────────
// The dry run fills the dialog with the counts, the debit/credit totals, the
// blockers and the warnings; the import only runs once the dry run is clean.
// Server side everything is re-validated (ledger_import.py), all or nothing.

const GL_IMPORT_METHOD = "erpnext.custom_modules.reports.ledger_import";
const GL_IMPORT_ROLES = ["Accounts Manager", "System Manager"];

function can_manage_import() {
	return GL_IMPORT_ROLES.some((role) => frappe.user_roles.includes(role));
}

function setup_import_actions(report) {
	if (!can_manage_import()) return;
	report.page.add_inner_button(__("Importer Grand Livre"), () => open_import_dialog());
	report.page.add_menu_item(__("Supprimer l'import"), () => delete_import_rows());
}

function delete_import_rows() {
	const context = (window.axeane && axeane.context && axeane.context.get()) || {};
	frappe.confirm(
		__(
			"Supprimer les lignes importees du contexte {0} · {1} ? Les lignes des ecritures ne sont pas touchees.",
			[context.entreprise_label || "—", context.exercice_label || "—"]
		),
		() => {
			frappe.call({
				method: GL_IMPORT_METHOD + ".delete_import",
				freeze: true,
				callback(r) {
					frappe.show_alert({
						message: __("Import supprime: {0} ligne(s).", [r.message ? r.message.deleted : 0]),
						indicator: "green",
					});
					frappe.query_report.refresh();
				},
			});
		}
	);
}

function open_import_dialog() {
	const context = (window.axeane && axeane.context && axeane.context.get()) || {};
	const dialog = new frappe.ui.Dialog({
		title: [__("Importer Grand Livre"), context.entreprise_label, context.exercice_label]
			.filter(Boolean)
			.join(" · "),
		fields: [
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("Fichier Excel (.xlsx)"),
				reqd: 1,
				description: __("Feuille unique: Date | Mvt | Compte | Libellé | Journal | Pièce | Débit | Crédit"),
			},
			{
				fieldname: "verify_html",
				fieldtype: "HTML",
				options: `<button class="btn btn-default btn-sm gl-import-verify">${__("Verifier")}</button>`,
			},
			{ fieldname: "summary", fieldtype: "HTML", options: "" },
			{
				fieldname: "create_journals",
				fieldtype: "Check",
				label: __("Creer les journaux manquants"),
				default: 1,
			},
			{
				fieldname: "replace",
				fieldtype: "Check",
				label: __("Remplacer l'import precedent"),
				default: 0,
				hidden: 1,
			},
		],
		primary_action_label: __("Importer"),
		primary_action: () => run_import(dialog),
	});
	dialog.show();
	dialog.disable_primary_action();
	dialog.$wrapper.find(".gl-import-verify").on("click", () => verify_file(dialog));
}

function verify_file(dialog) {
	const file_url = dialog.get_value("file");
	if (!file_url || !file_url.toLowerCase().endsWith(".xlsx")) {
		frappe.msgprint({ message: __("Choisissez un fichier Excel .xlsx."), indicator: "red" });
		return;
	}
	dialog.disable_primary_action();
	frappe.call({
		method: GL_IMPORT_METHOD + ".validate_grand_livre",
		args: { file_url },
		freeze: true,
		callback(r) {
			const validation = r.message || {};
			render_import_summary(dialog, validation);
			if (!(validation.blockers || []).length) {
				dialog.enable_primary_action();
			}
			// the previous import only matters when the user wants it replaced
			const replace_field = dialog.get_field("replace");
			replace_field.df.hidden = (validation.existing_import_rows || 0) === 0;
			replace_field.refresh();
		},
	});
}

function render_import_summary(dialog, validation) {
	const $area = dialog.fields_dict.summary.$wrapper;
	const esc = frappe.utils.escape_html;
	const blockers = validation.blockers || [];
	const warnings = validation.warnings || [];

	const stats = [
		{ label: __("Lignes"), value: validation.rows || 0 },
		{ label: __("Ecritures"), value: validation.entries || 0 },
		{ label: __("Comptes"), value: validation.accounts || 0 },
		{ label: __("Journaux"), value: validation.journals || 0 },
		{ label: __("Total Debit"), value: format_number(validation.total_debit || 0) },
		{ label: __("Total Credit"), value: format_number(validation.total_credit || 0) },
	];
	if (validation.date_min) {
		stats.push({ label: __("Periode"), value: `${validation.date_min} → ${validation.date_max}` });
	}
	const $stats = $('<div class="report-summary gl-import-stats"></div>');
	stats.forEach((item) =>
		$stats.append(
			frappe.utils.build_summary_item({
				label: item.label,
				value: item.value,
				datatype: "Data",
			})
		)
	);

	const list = (items) => `<ul class="gl-import-list">${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>`;
	let html = $stats.prop("outerHTML");
	if (blockers.length) {
		html += `<div class="alert alert-danger" style="margin-top: 8px;">${__("Bloquants")}${list(blockers)}</div>`;
	} else {
		html += `<div class="alert alert-success" style="margin-top: 8px;">${__(
			"Validation reussie: aucune anomalie bloquante."
		)}</div>`;
	}
	if (warnings.length) {
		html += `<div class="alert alert-warning" style="margin-top: 8px;">${__("Avertissements")}${list(warnings)}</div>`;
	}
	$area.html(html);
}

function run_import(dialog) {
	const file_url = dialog.get_value("file");
	if (!file_url) return;
	return frappe.call({
		method: GL_IMPORT_METHOD + ".import_grand_livre",
		args: {
			file_url,
			replace: dialog.get_value("replace") ? 1 : 0,
			create_journals: dialog.get_value("create_journals") ? 1 : 0,
		},
		freeze: true,
		callback(r) {
			const result = r.message || {};
			dialog.hide();
			const journals = (result.journals_created || []).join(", ");
			frappe.show_alert({
				message:
					__("Import termine: {0} ligne(s), {1} ecriture(s), lot {2}.", [
						result.inserted || 0,
						result.entries || 0,
						result.batch || "",
					]) + (journals ? " " + __("Journaux crees: {0}.", [journals]) : ""),
				indicator: "green",
			});
			// the freshly imported exercice reads best as a whole: Annuelle,
			// from the first page
			frappe.query_report.set_filter_value("period_type", "Annuelle");
			GL_PAGINATION.reset_page();
			frappe.query_report.refresh();
		},
	});
}
