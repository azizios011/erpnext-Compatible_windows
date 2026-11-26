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
//
// Nothing runs synchronously: at Annuelle scale the Grand Livre is ~32k rows
// / ~1,000 pages and the build takes minutes — a synchronous request can
// never survive it (that is what hung the views on "Generation du Grand
// Livre..."). The client calls the prepare endpoint (cache hit / size guard
// / background job start) and then POLLS the status endpoint until the job
// reports done / failed / cancelled; frappe.publish_realtime events only
// accelerate the progress text (polling is the fallback, a hard timeout the
// last resort). Every failure path renders an explicit error — the view can
// never spin forever.

const GL_DOC_API = {
	prepare: "print_designer.api.ledger_documents.prepare_grand_livre_document",
	status: "print_designer.api.ledger_documents.get_grand_livre_document_status",
	cancel: "print_designer.api.ledger_documents.cancel_grand_livre_document",
};
const GL_DOC_EVENT_PROGRESS = "grand_livre_document_progress";

const GL_VIEW_STATE = {
	active: "list",
	el: null,
	timer: null,
	generation: 0,
	cleanup: null,
	// the active generation: { kind, cache_key, started_at }
	poll: null,
};

// generous hard cap (measured: ~9 min of build at 32k rows + conversion)
const GL_DOC_HARD_TIMEOUT_MS = 30 * 60 * 1000;
const GL_DOC_POLL_MS = 1500;

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

const GL_PAGE_SIZE = 20;

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

// ── Row action icons (document / eye / pen) ──────────────────────────────────
// the narrow last column carries three small icon buttons per row: the
// document icon opens the attached file read-only (bundled pdf-editor page
// when the attachment is a File, new-tab fallback otherwise) and is enabled
// only when the transaction was entered with a Facturation document
// (source_doctype + source_name + an attachment); the eye icon opens the
// source entry in the Entries workspace in inspect mode; the pen icon opens
// the entry in modify mode (disabled when the entry cannot be modified —
// closed Exercice or lettered lines). All live in the page's dict
// (has_document / document_file / document_file_name /
// source_entry_doctype / source_entry) — resolved server-side in ONE
// batched query per source_doctype group.

function gl_exercice_is_closed() {
	// the boot context carries every Exercice of the Entreprise with its
	// status; all rows of this report belong to the selected Exercice
	const context = (window.axeane && axeane.context && axeane.context.get()) || {};
	const exercice = (context.exercices || []).find((item) => item.name === context.exercice);
	return !!(exercice && exercice.status && exercice.status !== "Ouvert");
}

function gl_row_actions(data) {
	const esc = frappe.utils.escape_html;
	const doc_enabled = data.has_document && (data.document_file_name || data.document_file);
	const entry_enabled = data.source_entry_doctype && data.source_entry;
	const modify_disabled = !entry_enabled || !!data.lettrage || gl_exercice_is_closed();
	const document_button = `<button type="button" class="btn btn-xs gl-row-action gl-doc-open${
		doc_enabled ? "" : " gl-action-disabled"
	}" title="${__("Voir le document")}"${doc_enabled ? "" : " disabled"} data-file-name="${esc(
		data.document_file_name || ""
	)}" data-file-url="${esc(data.document_file || "")}">
		${frappe.utils.icon("file", "xs")}
	</button>`;
	const entry_button = `<button type="button" class="btn btn-xs gl-row-action gl-entry-open${
		entry_enabled ? "" : " gl-action-disabled"
	}" title="${__("Inspecter l'ecriture")}"${entry_enabled ? "" : " disabled"} data-entry-doctype="${esc(
		data.source_entry_doctype || ""
	)}" data-entry="${esc(data.source_entry || "")}">
		${frappe.utils.icon("eye", "xs")}
	</button>`;
	const modify_button = `<button type="button" class="btn btn-xs gl-row-action gl-entry-edit${
		modify_disabled ? " gl-action-disabled" : ""
	}" title="${__("Modifier l'ecriture")}"${modify_disabled ? " disabled" : ""} data-entry-doctype="${esc(
		data.source_entry_doctype || ""
	)}" data-entry="${esc(data.source_entry || "")}">
		${frappe.utils.icon("pencil", "xs")}
	</button>`;
	return `<span class="gl-row-actions">${document_button}${entry_button}${modify_button}</span>`;
}

function gl_open_document(file_name, file_url) {
	// the bundled pdf-editor page on the File doc, read-only; the raw url in
	// a new tab when there is no File docname to hand over
	if (file_name) {
		window.open(`/app/pdf-editor?file=${encodeURIComponent(file_name)}`, "_blank");
		return;
	}
	if (file_url) window.open(file_url, "_blank");
}

function gl_doc_filters() {
	return JSON.stringify(frappe.query_report.get_filter_values() || {});
}

function gl_doc_call(method, args) {
	// one place for the POST whitelisted calls; resolves the payload
	return new Promise((resolve, reject) => {
		frappe
			.call({ method, args, type: "POST" })
			.then((r) => resolve(r.message || {}))
			.catch((err) => reject(err));
	});
}

function gl_trigger_download(result, kind) {
	if (!result || !result.file_url) return;
	const anchor = document.createElement("a");
	anchor.href = result.file_url + (result.file_url.includes("?") ? "&" : "?") + "v=" + Date.now();
	anchor.download = result.name || "grand-livre." + kind;
	document.body.appendChild(anchor);
	anchor.click();
	anchor.remove();
}

function gl_view_toolbar(kind, status_html, with_cancel) {
	const esc = frappe.utils.escape_html;
	// downloads / print live in the page header (gl_doc_header_controls);
	// the in-view toolbar carries only the status line and the Cancel
	return `
		<div class="gl-doc-toolbar" style="
			display: flex; align-items: center; gap: 8px;
			padding: 8px 10px; border-bottom: 1px solid var(--border-color, #d1d8dd);
			background: var(--bg-color, #fff);
		">
			<span class="gl-doc-status text-muted" style="font-size: 12px;">${esc(status_html)}</span>
			<span style="flex: 1;"></span>
			<button class="btn btn-xs btn-default gl-doc-cancel"${with_cancel ? "" : " style=\"display: none;\""}>
				${__("Annuler")}
			</button>
		</div>`;
}

// ── document-view header controls (Filtres / Pages / progress / downloads) ──
// built once per mount, removed on unmount (the buttons' listeners die with
// the node — no leaked iframes or listeners across view switches)

function gl_doc_header_controls(kind) {
	const $group = $(`
		<div class="btn-group gl-doc-controls" role="group" style="margin-right: 8px;">
			<button type="button" class="btn btn-default btn-sm gl-filters-toggle">${__("Filtres")}</button>
			<span class="gl-doc-pages btn btn-default btn-sm disabled" style="display: none;"></span>
			<span class="gl-doc-progress text-muted small" style="padding: 0 8px; align-self: center;"></span>
			<button type="button" class="btn btn-default btn-sm gl-download-xlsx">${__("Telecharger .xlsx")}</button>
			<button type="button" class="btn btn-default btn-sm gl-download-pdf">${__("Telecharger .pdf")}</button>
			${kind === "pdf" ? `<button type="button" class="btn btn-default btn-sm gl-print-pdf">${__("Imprimer")}</button>` : ""}
		</div>`);
	$group.find(".gl-filters-toggle").on("click", () => {
		const open = report_page_main().toggleClass("gl-filters-open").hasClass("gl-filters-open");
		$group.find(".gl-filters-toggle").toggleClass("btn-primary", open);
	});
	$group.find(".gl-download-xlsx").on("click", () => gl_download_document("xlsx"));
	$group.find(".gl-download-pdf").on("click", () => gl_download_document("pdf"));
	$group.find(".gl-print-pdf").on("click", () => {
		// print the SAME document the view renders (same-origin editor iframe)
		const el = GL_VIEW_STATE.el;
		const iframe = el && el.querySelector("iframe");
		try {
			iframe && iframe.contentWindow && iframe.contentWindow.print();
		} catch (error) {
			console.error("ledger_data: print failed", error);
			frappe.msgprint({ message: __("L'impression n'est pas disponible ici."), indicator: "red" });
		}
	});
	return $group;
}

function report_page_main() {
	const qr = frappe.query_report;
	return qr && qr.page && qr.page.main ? qr.page.main : $();
}

function gl_doc_header_mount(kind) {
	const main = report_page_main();
	if (!main.length) return;
	main.find(".custom-actions").find(".gl-doc-controls").remove();
	const $group = gl_doc_header_controls(kind);
	// before the view switcher, at the left edge of the header actions
	main.find(".custom-actions").find(".view-switcher").before($group);
}

function gl_doc_header_unmount() {
	const main = report_page_main();
	main.find(".custom-actions").find(".gl-doc-controls").remove();
	main.removeClass("gl-filters-open"); // a left-open overlay never leaks
}

function gl_doc_header_pages(pages) {
	const main = report_page_main();
	const $badge = main.find(".gl-doc-controls .gl-doc-pages");
	if ($badge.length) {
		$badge.text(`${__("Pages")}: ${pages}`).show();
	}
}

function gl_doc_header_progress(text) {
	const main = report_page_main();
	const $span = main.find(".gl-doc-controls .gl-doc-progress");
	if ($span.length) $span.text(text || "");
}

function gl_doc_set_status(el, text) {
	const $status = el.querySelector(".gl-doc-status");
	if ($status) $status.textContent = text;
	gl_doc_header_progress(text);
}

function gl_doc_set_cancel(el, visible) {
	const button = el.querySelector(".gl-doc-cancel");
	if (button) button.style.display = visible ? "" : "none";
}

function gl_download_document(kind) {
	// menu / toolbar download: same background job, then the browser saves
	// the file as soon as the state reports done
	const filters = gl_doc_filters();
	gl_doc_call(GL_DOC_API.prepare, { filters, kind, force: 1 })
		.then((result) => {
			if (result.status === "done" && result.file_url) {
				gl_trigger_download(result, kind);
				return;
			}
			if (result.status === "error") {
				frappe.msgprint({ message: result.error, indicator: "red" });
				return;
			}
			if (result.status === "too_large") {
				frappe.msgprint({
					message: __("{0} lignes (~{1} pages): choisissez un mois ou un compte.", [
						result.rows,
						result.pages,
					]),
					indicator: "orange",
				});
				return;
			}
			// queued: poll with a progress dialog (no freeze — the job takes
			// minutes and the dialog stays cancelable-by-browser-tab)
			const started_at = Date.now();
			frappe.show_progress(__("Grand Livre"), 20, 300, __("Generation en tache de fond..."));
			const tick = () => {
				gl_doc_call(GL_DOC_API.status, { cache_key: result.cache_key, kind })
					.then((state) => {
						if (state.status === "done" && state.file_url) {
							frappe.hide_progress();
							gl_trigger_download(state, kind);
							return;
						}
						if (["failed", "unknown", "cancelled"].includes(state.status)) {
							frappe.hide_progress();
							frappe.msgprint({
								message:
									state.error ||
									__(
										"La generation a ete annulee ou perdue: reessayez."
									),
								indicator: "red",
							});
							return;
						}
						if (Date.now() - started_at > GL_DOC_HARD_TIMEOUT_MS) {
							frappe.hide_progress();
							frappe.msgprint({ message: gl_doc_timeout_message(), indicator: "red" });
							return;
						}
						if (state.progress) frappe.show_progress(__("Grand Livre"), 20, 300, state.progress);
						setTimeout(tick, GL_DOC_POLL_MS);
					})
					.catch(() => {
						// transient network error: keep polling until the hard cap
						if (Date.now() - started_at > GL_DOC_HARD_TIMEOUT_MS) {
							frappe.hide_progress();
							frappe.msgprint({ message: gl_doc_timeout_message(), indicator: "red" });
							return;
						}
						setTimeout(tick, GL_DOC_POLL_MS);
					});
			};
			setTimeout(tick, GL_DOC_POLL_MS);
		})
		.catch(() => frappe.msgprint({ message: __("La generation a echoue. Reessayez."), indicator: "red" }));
}

function gl_doc_timeout_message() {
	return __(
		"La generation depasse {0} minutes: reessayez ou reduisez la periode.",
		[Math.round(GL_DOC_HARD_TIMEOUT_MS / 60000)]
	);
}

function gl_doc_error_panel(el, kind, message, with_xlsx_fallback) {
	// every failure path lands here: message + Retry (+ .xlsx fallback on
	// the PDF view when LibreOffice is missing) — never a silent loading
	const esc = frappe.utils.escape_html;
	const area = el.querySelector(".gl-doc-frame-area");
	gl_doc_set_cancel(el, false);
	gl_doc_header_progress(message);
	if (!area) return;
	area.innerHTML = `
		<div style="position: absolute; inset: 0; display: flex; flex-direction: column;
			align-items: center; justify-content: center; gap: 12px; text-align: center; padding: 20px;">
			<div class="text-muted" style="max-width: 480px;">${esc(message)}</div>
			<div style="display: flex; gap: 8px;">
				<button class="btn btn-sm btn-primary gl-doc-retry">${__("Reessayer")}</button>
				${with_xlsx_fallback ? `<button class="btn btn-sm btn-default gl-doc-fallback-xlsx">${__("Telecharger .xlsx")}</button>` : ""}
			</div>
		</div>`;
	const retry = area.querySelector(".gl-doc-retry");
	if (retry) retry.addEventListener("click", () => gl_mount_document(el, kind));
	const fallback = area.querySelector(".gl-doc-fallback-xlsx");
	if (fallback) fallback.addEventListener("click", () => gl_download_document("xlsx"));
}

function gl_doc_too_large_panel(el, kind, result) {
	// the size guard: do NOT auto-generate a huge document — the banner
	// offers the explicit override instead
	const esc = frappe.utils.escape_html;
	const area = el.querySelector(".gl-doc-frame-area");
	gl_doc_set_cancel(el, false);
	gl_doc_header_progress(
		__("{0} lignes (~{1} pages): choisissez un mois ou un compte.", [result.rows, result.pages])
	);
	if (!area) return;
	area.innerHTML = `
		<div class="alert alert-warning" style="position: absolute; top: 20px; left: 20px; right: 20px;
			display: flex; align-items: center; justify-content: space-between; gap: 12px;">
			<span>${esc(
				__("{0} lignes (~{1} pages): choisissez un mois ou un compte.", [result.rows, result.pages])
			)}</span>
			<button class="btn btn-sm btn-warning gl-doc-force">${__("Generer quand meme")}</button>
		</div>`;
	const force = area.querySelector(".gl-doc-force");
	if (force) force.addEventListener("click", () => gl_mount_document(el, kind, 1));
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
				// grid only: no ribbon, no formula bar, no sheet tabs, no save
				mode: "preview",
			},
			window.location.origin
		);
	};
	window.addEventListener("message", on_message);
	GL_VIEW_STATE.cleanup = () => window.removeEventListener("message", on_message);
	iframe.src = "/assets/print_designer/editors/sheets/index.html";
}

function gl_mount_pdf_editor(area, file_docname) {
	// the STANDALONE bundled pdf editor (the same one the /app/pdf-editor
	// desk page iframes) in read-only preview mode: page canvas, scroll,
	// zoom and the page indicator only — no toolbar, sidebars, search or
	// save. Iframing the desk page would nest a whole second desk (Print
	// Designer sidebar, page head). Same handshake as gl_mount_sheets_editor
	// and the desk page (print_designer/page/pdf_editor): the editor signals
	// pdf-editor-ready on every boot, the host replies pdf-editor-init with
	// the same payload the desk page sends. Same-origin (served from
	// /assets): Print (header control) reaches the iframe.
	const iframe = document.createElement("iframe");
	iframe.title = __("Grand Livre PDF");
	iframe.style.cssText = "border: 0; width: 100%; height: 100%; display: block;";
	area.appendChild(iframe);
	const on_message = (ev) => {
		if (ev.source !== iframe.contentWindow) return;
		const data = ev.data || {};
		if (data.type !== "pdf-editor-ready") return;
		iframe.contentWindow.postMessage(
			{
				type: "pdf-editor-init",
				file: file_docname,
				lang: frappe.boot.lang || "en",
				csrfToken: frappe.csrf_token,
				fullName: frappe.user_info(frappe.session.user).fullname,
				// the preview mode strips every editing surface (ribbon,
				// sidebars, search, save) — posted ledger data is read-only
				mode: "preview",
			},
			window.location.origin
		);
	};
	window.addEventListener("message", on_message);
	GL_VIEW_STATE.cleanup = () => window.removeEventListener("message", on_message);
	iframe.src = "/assets/print_designer/editors/pdf/index.html";
}

function gl_doc_mount_result(el, kind, result) {
	// done: the page count lives ONLY in the header badge (gl-doc-pages) —
	// the in-view toolbar goes away, the viewer takes the whole frame area
	gl_doc_set_cancel(el, false);
	gl_doc_header_pages(result.pages || "?");
	gl_doc_header_progress("");
	const toolbar = el.querySelector(".gl-doc-toolbar");
	if (toolbar) toolbar.remove();
	const area = el.querySelector(".gl-doc-frame-area");
	if (!area) return;
	area.innerHTML = "";
	if (kind === "xlsx") {
		gl_mount_sheets_editor(area, result.file);
	} else if (result.file) {
		// the standalone bundled pdf editor in read-only PREVIEW mode (never
		// a plain browser PDF iframe, never the nested desk page): full
		// screen under the page header
		gl_mount_pdf_editor(area, result.file);
	} else {
		gl_doc_error_panel(el, kind, __("Le document n'a pas de fichier associe."), false);
	}
}

function gl_doc_poll(el, kind, generation, cache_key) {
	// the polling loop: never trust a single realtime event, never wait
	// forever — the hard timeout ends the wait with a clear error
	const state = GL_VIEW_STATE;
	const tick = () => {
		if (generation !== state.generation || state.active !== kind) return; // unmounted / remounted
		gl_doc_call(GL_DOC_API.status, { cache_key, kind })
			.then((result) => {
				if (generation !== state.generation || state.active !== kind) return;
				if (result.status === "done" && result.file_url) {
					gl_doc_mount_result(el, kind, result);
					return;
				}
				if (result.status === "failed") {
					gl_doc_error_panel(el, kind, result.error || __("La generation a echoue. Reessayez."), kind === "pdf");
					return;
				}
				if (result.status === "cancelled") {
					gl_doc_error_panel(el, kind, __("Generation annulee."), false);
					return;
				}
				if (result.status === "unknown") {
					// the cache entry is gone (redis flushed): retry cleanly
					gl_doc_error_panel(el, kind, __("La generation a ete perdue: reessayez."), false);
					return;
				}
				if (Date.now() - state.poll.started_at > GL_DOC_HARD_TIMEOUT_MS) {
					gl_doc_error_panel(el, kind, gl_doc_timeout_message(), false);
					return;
				}
				if (result.progress) gl_doc_set_status(el, result.progress);
				state.timer = setTimeout(tick, GL_DOC_POLL_MS);
			})
			.catch(() => {
				// transient network error: keep polling until the hard cap
				if (generation !== state.generation || state.active !== kind) return;
				if (Date.now() - state.poll.started_at > GL_DOC_HARD_TIMEOUT_MS) {
					gl_doc_error_panel(el, kind, gl_doc_timeout_message(), false);
					return;
				}
				state.timer = setTimeout(tick, GL_DOC_POLL_MS);
			});
	};
	state.timer = setTimeout(tick, GL_DOC_POLL_MS);
}

function gl_hide_native_chrome() {
	// while a document view is on screen, the native report pieces never
	// show above the viewer: the report wrapper / empty state ("Nothing to
	// show"), the prepared-report / stale status band ("This report was
	// generated N minutes ago"), the server message, the loading band and
	// the hint footer. frappe's refresh flow re-shows them — the shared
	// after_refresh hook (report_views.bundle.js) re-hides after every
	// refresh; this covers the mount itself.
	const qr = frappe.query_report;
	if (!qr) return;
	[qr.$report, qr.$message, qr.$status, qr.$report_message, qr.$loading].forEach(
		($el) => $el && $el.hide && $el.hide()
	);
	if (qr.$report_footer) qr.$report_footer.hide();
}

function gl_mount_document(el, kind, force) {
	// one generation at a time; stale callbacks never mount
	const generation = ++GL_VIEW_STATE.generation;
	GL_VIEW_STATE.active = kind;
	GL_VIEW_STATE.el = el;
	GL_VIEW_STATE.poll = null;
	if (GL_VIEW_STATE.cleanup) {
		GL_VIEW_STATE.cleanup();
		GL_VIEW_STATE.cleanup = null;
	}
	if (GL_VIEW_STATE.timer) {
		clearTimeout(GL_VIEW_STATE.timer);
		GL_VIEW_STATE.timer = null;
	}
	gl_hide_native_chrome();
	el.innerHTML = `
		<div class="gl-doc-view" style="
			display: flex; flex-direction: column; width: 100%; height: 100%;
		">
			${gl_view_toolbar(kind, __("Generation en cours..."), false)}
			<div class="gl-doc-frame-area" style="flex: 1; position: relative; min-height: 0;">
				<div class="gl-doc-loading text-muted" style="
					position: absolute; inset: 0; display: flex;
					align-items: center; justify-content: center;
				">${__("Generation du Grand Livre...")}</div>
			</div>
		</div>`;
	gl_doc_header_mount(kind);
	el.querySelector(".gl-doc-cancel").addEventListener("click", () => {
		const poll = GL_VIEW_STATE.poll;
		if (!poll) return;
		gl_doc_call(GL_DOC_API.cancel, { cache_key: poll.cache_key, kind }).catch(() => {});
		gl_doc_error_panel(el, kind, __("Generation annulee."), false);
	});

	gl_doc_call(GL_DOC_API.prepare, { filters: gl_doc_filters(), kind, force: force ? 1 : 0 })
		.then((result) => {
			if (generation !== GL_VIEW_STATE.generation || GL_VIEW_STATE.active !== kind) return;
			if (result.status === "done" && result.file_url) {
				gl_doc_mount_result(el, kind, result);
				return;
			}
			if (result.status === "error") {
				gl_doc_error_panel(el, kind, result.error, kind === "pdf");
				return;
			}
			if (result.status === "too_large") {
				gl_doc_too_large_panel(el, kind, result);
				return;
			}
			// queued / running: poll the status endpoint; the realtime
			// progress events only refresh the text faster (fallback = poll)
			GL_VIEW_STATE.poll = { kind, cache_key: result.cache_key, started_at: Date.now() };
			gl_doc_set_cancel(el, true);
			gl_doc_set_status(el, result.progress || __("Generation en tache de fond..."));
			const on_progress = (event) => {
				if (
					event &&
					event.cache_key === result.cache_key &&
					generation === GL_VIEW_STATE.generation &&
					GL_VIEW_STATE.active === kind
				) {
					gl_doc_set_status(el, event.progress || "");
				}
			};
			frappe.realtime.on(GL_DOC_EVENT_PROGRESS, on_progress);
			GL_VIEW_STATE.cleanup = () => frappe.realtime.off(GL_DOC_EVENT_PROGRESS, on_progress);
			gl_doc_poll(el, kind, generation, result.cache_key);
		})
		.catch(() => {
			if (generation !== GL_VIEW_STATE.generation || GL_VIEW_STATE.active !== kind) return;
			gl_doc_error_panel(el, kind, __("La generation a echoue. Reessayez."), false);
		});
}

function gl_unmount_document() {
	GL_VIEW_STATE.active = "list";
	gl_doc_header_unmount();
	if (GL_VIEW_STATE.el) {
		GL_VIEW_STATE.el.innerHTML = "";
		GL_VIEW_STATE.el = null;
	}
	GL_VIEW_STATE.generation += 1; // a stale callback never mounts
	GL_VIEW_STATE.poll = null;
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

// ── Single header row (merged title + filter) ────────────────────────────────
// Called from after_datatable_render: the dt-row-header is hidden by CSS
// (report_views.bundle.js scoped to .report-gl-fill); here we set each
// filter input's placeholder to the column label and add a sort icon next to
// every filterable column. The actions column gets no input. Survives every
// re-render, fluid layout, and the filters-toggle states.

const GL_SORT_ICON_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24"
	fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
	class="gl-sort-icon"><path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/></svg>`;

function gl_setup_single_header_row(report) {
	const datatable = report.datatable;
	if (!datatable || !datatable.header) return;
	const $header = $(datatable.header);
	const $filterRow = $header.find(".dt-row-filter");
	if (!$filterRow.length) return;

	const columns = datatable.getColumns ? datatable.getColumns() : [];

	$filterRow.find(".dt-cell").each(function () {
		const $cell = $(this);
		const $content = $cell.find(".dt-cell__content");
		const $input = $cell.find(".dt-filter.dt-input");
		const colIndex = parseInt($cell.attr("data-col-index"), 10);
		const col = columns[colIndex];

		// actions column: hide the input entirely
		if (col && (col.id === "actions" || col.fieldname === "actions")) {
			$input.hide();
			return;
		}

		// set placeholder to the column label
		if (col && $input.length) {
			const label = col.name || col.content || "";
			$input.attr("placeholder", label);
		}

		// add resize handle so native datatable resize works on filter cells
		if (col && !$content.find(".dt-cell__resize-handle").length) {
			$content.append('<span class="dt-cell__resize-handle"></span>');
		}

		// add a sort icon if not already present and update its state
		if (col) {
			let $sort = $content.find(".gl-col-sort");
			if (!$sort.length) {
				$sort = $(`<span class="gl-col-sort" data-col-index="${colIndex}" title="${__("Tri")}">${GL_SORT_ICON_SVG}</span>`);
				$content.append($sort);
			}
			const sortOrder = col.sortOrder || "none";
			const isSorted = sortOrder === "asc" || sortOrder === "desc";
			$sort.find(".gl-sort-icon").toggleClass("active", isSorted);
			if (isSorted) {
				$sort.attr("title", sortOrder === "asc" ? __("Tri croissant") : __("Tri decroissant"));
			} else {
				$sort.attr("title", __("Tri"));
			}
		}
	});

	if (!datatable._gl_sort_hooked) {
		datatable._gl_sort_hooked = true;
		datatable.on("onSortColumn", () => {
			gl_setup_single_header_row(report);
		});
	}

	// delegated sort click handler (idempotent: off+on)
	$header
		.off("click.gl-sort")
		.on("click.gl-sort", ".gl-col-sort", function (e) {
			e.preventDefault();
			e.stopPropagation();
			const colIndex = parseInt($(this).attr("data-col-index"), 10);
			if (isNaN(colIndex)) return;
			const col = datatable.getColumn ? datatable.getColumn(colIndex) : columns[colIndex];
			const currentOrder = (col && col.sortOrder) || "none";
			const nextOrder = currentOrder === "asc" ? "desc" : "asc";
			datatable.sortColumn(colIndex, nextOrder);
		});
}

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
			options: "Tous les comptes\nSaisie libre\nCompte\nIntervalle des comptes\nComptes non soldes",
			default: "Tous les comptes",
			reqd: 1,
			on_change: gl_filter_changed,
		},
		{
			fieldname: "account",
			label: __("Compte"),
			fieldtype: "Autocomplete",
			depends_on: "eval:doc.extract_type == 'Compte'",
			get_data(txt) {
				return frappe
					.xcall("erpnext.custom_modules.organization.tiers_accounts.compte_search", {
						doctype: "Chart of Account",
						txt: txt || "",
						searchfield: "name",
						start: 0,
						page_len: 500,
					})
					.then((rows) =>
						(rows || []).map((r) => ({
							label: `${r.account_number} · ${r.account_name}`,
							value: r.name,
						}))
					);
			},
			on_change: gl_filter_changed,
		},
		{
			fieldname: "from_account",
			label: __("Du compte"),
			fieldtype: "Autocomplete",
			depends_on: "eval:doc.extract_type == 'Intervalle des comptes'",
			get_data(txt) {
				return frappe
					.xcall("erpnext.custom_modules.organization.tiers_accounts.compte_search", {
						doctype: "Chart of Account",
						txt: txt || "",
						searchfield: "name",
						start: 0,
						page_len: 500,
					})
					.then((rows) =>
						(rows || []).map((r) => ({
							label: `${r.account_number} · ${r.account_name}`,
							value: r.account_number,
						}))
					);
			},
			on_change: gl_filter_changed,
		},
		{
			fieldname: "to_account",
			label: __("Au compte"),
			fieldtype: "Autocomplete",
			depends_on: "eval:doc.extract_type == 'Intervalle des comptes'",
			get_data(txt) {
				return frappe
					.xcall("erpnext.custom_modules.organization.tiers_accounts.compte_search", {
						doctype: "Chart of Account",
						txt: txt || "",
						searchfield: "name",
						start: 0,
						page_len: 500,
					})
					.then((rows) =>
						(rows || []).map((r) => ({
							label: `${r.account_number} · ${r.account_name}`,
							value: r.account_number,
						}))
					);
			},
			on_change: gl_filter_changed,
		},
		{
			fieldname: "saisie_libre",
			label: __("Saisie libre"),
			fieldtype: "Data",
			depends_on: "eval:doc.extract_type == 'Saisie libre'",
			description: __("Ex: 401, 411000, 512-531"),
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
		// the whole body is wrapped: ONE bad cell must never blank the table
		// (a throw inside a cell formatter aborts the virtual scroller's
		// chunk render). On error: log the column + row, fall back to the
		// default formatter, then to the escaped plain value.
		try {
			// the MVT of the entry doctypes opens the entry in inspect mode
			// through erpnext.entries.open_entry — in both views.
			// Header, opening and total rows carry no source_entry: default.
			if (
				column.id === "mvt" &&
				data &&
				data.source_entry &&
				["Payable Transaction", "Receivable Transaction", "Treasury Transaction", "Declaration Transaction"].includes(data.source_entry_doctype)
			) {
				return `<a href="#" class="gl-mvt-link" data-entry-doctype="${frappe.utils.escape_html(
					data.source_entry_doctype
				)}" data-entry="${frappe.utils.escape_html(data.source_entry)}">${frappe.utils.escape_html(value)}</a>`;
			}
			if (column.id === "actions" && data) {
				// the narrow action-icon column: document / eye / pen, greyed when the
				// row carries no attachment / no source entry / entry is lettered
				return gl_row_actions(data);
			}
			return default_formatter(value, row, column, data);
		} catch (error) {
			console.error(
				"ledger_data: cell formatter failed for column",
				column && column.id,
				"row",
				row && row.meta ? row.meta.rowIndex : row,
				error
			);
			try {
				return default_formatter(value, row, column, data);
			} catch (fallback_error) {
				console.error("ledger_data: default formatter failed too", fallback_error);
				return frappe.utils.escape_html(value == null ? "" : String(value));
			}
		}
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

		// the row action icons (delegated: the datatable re-renders cells;
		// disabled buttons carry the gl-action-disabled class and never fire)
		report.$report
			.off("click.gl-doc-open")
			.on("click.gl-doc-open", ".gl-doc-open", function (event) {
				event.preventDefault();
				event.stopPropagation();
				if (this.disabled) return;
				gl_open_document($(this).attr("data-file-name"), $(this).attr("data-file-url"));
			});
		report.$report
			.off("click.gl-entry-open")
			.on("click.gl-entry-open", ".gl-entry-open", function (event) {
				event.preventDefault();
				event.stopPropagation();
				if (this.disabled) return;
				erpnext.entries.open_entry({
					entry_doctype: $(this).attr("data-entry-doctype"),
					name: $(this).attr("data-entry"),
					mode: "inspect",
				});
			});
		report.$report
			.off("click.gl-entry-edit")
			.on("click.gl-entry-edit", ".gl-entry-edit", function (event) {
				event.preventDefault();
				event.stopPropagation();
				if (this.disabled) return;
				erpnext.entries.open_entry({
					entry_doctype: $(this).attr("data-entry-doctype"),
					name: $(this).attr("data-entry"),
					mode: "modify",
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
				fill_datatable: true,
				summary_position: "top",
				hide_filters_in_doc: true,
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

		// a render that throws must be VISIBLE, not a silent blank table: the
		// patched render_datatable surfaces the error inline (red banner at
		// the top of the report body) and re-raises so frappe's promise chain
		// still runs its cleanup
		const gl_show_render_error = (error) => {
			const text = frappe.utils.escape_html(String((error && error.message) || error || "unknown error"));
			console.error("ledger_data: datatable render failed", error);
			report.$report.show();
			report.$report.html(
				`<div class="alert alert-danger gl-render-error" style="margin: 15px;">${__(
					"Le rendu du tableau a echoue"
				)}: <code>${text}</code></div>`
			);
		};
		const render_datatable_original = report.render_datatable;
		report.render_datatable = function () {
			try {
				render_datatable_original.apply(this, arguments);
			} catch (error) {
				gl_show_render_error(error);
				throw error;
			}
		};

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
		// state). The list view keeps the native refresh below. The whole
		// chain is guarded: a throw here would abort the refresh promise.
		const previous_after_render = report.report_settings.after_datatable_render;
		report.report_settings.after_datatable_render = () => {
			try {
				if (previous_after_render) previous_after_render();
				gl_remount_after_refresh();
				gl_setup_single_header_row(report);
			} catch (error) {
				console.error("ledger_data: after_datatable_render failed", error);
				gl_show_render_error(error);
			}
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
const GL_MATERIALIZE_METHOD = "erpnext.custom_modules.reports.imported_entries";
const GL_MATERIALIZE_EVENT = "grand_livre_materialize_progress";
const GL_IMPORT_ROLES = ["Accounts Manager", "System Manager"];

function can_manage_import() {
	return GL_IMPORT_ROLES.some((role) => frappe.user_roles.includes(role));
}

function setup_import_actions(report) {
	if (!can_manage_import()) return;
	report.page.add_inner_button(__("Importer Grand Livre"), () => open_import_dialog());
	report.page.add_menu_item(__("Generer les ecritures de l'import"), () => open_materialize_dialog());
	report.page.add_menu_item(__("Supprimer l'import"), () => delete_import_rows());

	// the materialize job's progress toasts: one persistent listener, no
	// stacking on re-onload
	frappe.realtime.off(GL_MATERIALIZE_EVENT);
	frappe.realtime.on(GL_MATERIALIZE_EVENT, (event) => {
		if (event && event.progress) {
			frappe.show_alert({ message: event.progress, indicator: "blue" });
		}
	});
}

function delete_import_rows() {
	const context = (window.axeane && axeane.context && axeane.context.get()) || {};
	frappe.confirm(
		__(
			"Supprimer les lignes importees du contexte {0} · {1} ? Les ecritures generees de l'import sont supprimees aussi.",
			[context.entreprise_label || "—", context.exercice_label || "—"]
		),
		() => {
			frappe.call({
				method: GL_IMPORT_METHOD + ".delete_import",
				freeze: true,
				callback(r) {
					const result = r.message || {};
					frappe.show_alert({
						message: __("Import supprime: {0} ligne(s), {1} ecriture(s).", [
							result.deleted || 0,
							result.entries_deleted || 0,
						]),
						indicator: "green",
					});
					frappe.query_report.refresh();
				},
			});
		}
	);
}

// ── Generer les ecritures de l'import ────────────────────────────────────────
// every imported movement becomes one transaction in the Entries workspace:
// the dry run shows the counts per doctype / per journal / unclassified
// first, and the real run goes through a long background job (progress via
// realtime toasts). Idempotent: rows already linked are skipped.

function open_materialize_dialog() {
	const context = (window.axeane && axeane.context && axeane.context.get()) || {};
	frappe.call({
		method: GL_MATERIALIZE_METHOD + ".materialize_imported_entries",
		args: { dry_run: 1 },
		freeze: true,
		freeze_message: __("Analyse des mouvements importes..."),
	})
		.then((r) => {
			const result = r.message || {};
			frappe.confirm(
				render_materialize_summary(result, context),
				() => enqueue_materialize(),
				() => {}
			);
		})
		.catch(() => frappe.msgprint({ message: __("L'analyse a echoue."), indicator: "red" }));
}

function render_materialize_summary(result, context) {
	const esc = frappe.utils.escape_html;
	const stats = [
		{ label: __("Mouvements a traiter"), value: result.groups_total || 0 },
		{ label: __("Lignes non liees"), value: result.rows_total || 0 },
		{ label: __("Lignes deja liees"), value: result.rows_already_linked || 0 },
		{ label: __("Payable Transaction"), value: (result.created || {})["Payable Transaction"] || 0 },
		{ label: __("Receivable Transaction"), value: (result.created || {})["Receivable Transaction"] || 0 },
		{ label: __("Treasury Transaction"), value: (result.created || {})["Treasury Transaction"] || 0 },
		{ label: __("Non classes"), value: result.unclassified_groups || 0 },
		{ label: __("Conflits de nom"), value: result.skipped_name_conflict || 0 },
	];
	if (result.groups_with_multiple_refs_or_dates) {
		stats.push({ label: __("Plusieurs refs/dates"), value: result.groups_with_multiple_refs_or_dates });
	}
	const $stats = $('<div class="report-summary gl-import-stats"></div>');
	stats.forEach((item) =>
		$stats.append(frappe.utils.build_summary_item({ label: item.label, value: item.value, datatype: "Data" }))
	);

	const rows = Object.entries(result.per_journal || {})
		.map(
			([journal, counts]) =>
				`<tr><td>${esc(journal)}</td><td>${counts["Payable Transaction"] || 0}</td><td>${
					counts["Receivable Transaction"] || 0
				}</td><td>${counts["Treasury Transaction"] || 0}</td><td>${counts.unclassified || 0}</td></tr>`
		)
		.join("");
	const table = `
		<table class="table table-bordered" style="margin-top: 8px;">
			<thead><tr><th>${__("Journal")}</th><th>${__("Payable")}</th><th>${__("Receivable")}</th><th>${__("Treasury")}</th><th>${__("Non classe")}</th></tr></thead>
			<tbody>${rows}</tbody>
		</table>`;
	const note = result.unclassified_groups
		? `<div class="alert alert-warning" style="margin-top: 8px;">${__(
				"{0} groupe(s) sans ligne auxiliaire (soldes d'ouverture, banque, taxes...) restent non lies.",
				[result.unclassified_groups]
			)}</div>`
		: "";
	return (
		`<h5>${__("Generer les ecritures de l'import")} · ${esc(
			[context.entreprise_label, context.exercice_label].filter(Boolean).join(" · ") || ""
		)}</h5>` +
		$stats.prop("outerHTML") +
		table +
		note
	);
}

function enqueue_materialize() {
	frappe.call({
		method: GL_MATERIALIZE_METHOD + ".enqueue_materialize_imported_entries",
		type: "POST",
		callback(r) {
			const result = r.message || {};
			if (result.error) {
				frappe.msgprint({ message: result.error, indicator: "red" });
				return;
			}
			frappe.show_alert({
				message: __("Generation des ecritures lancee en tache de fond (progression en notification)."),
				indicator: "blue",
			});
		},
	});
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
			if (result.materialize_enqueued) {
				frappe.show_alert({
					message: __("Generation des ecritures de l'import lancee en tache de fond."),
					indicator: "blue",
				});
			}
			// the freshly imported exercice reads best as a whole: Annuelle,
			// from the first page
			frappe.query_report.set_filter_value("period_type", "Annuelle");
			GL_PAGINATION.reset_page();
			frappe.query_report.refresh();
		},
	});
}
