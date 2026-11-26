// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Suppression Ecritures", {
	refresh(frm) {
		frm.disable_save();
		frm.page.set_title(__("Suppression des Ecritures"));
		if (!frm._se_initialized) {
			frm._se_initialized = true;
			init_suppression(frm);
		}
	},
});

function init_suppression(frm) {
	// ── state ──
	const state = {
		page: 1,
		page_size: 20,
		rows: [],
		total: 0,
		selected: new Map(),   // key = "doctype::name"
		select_all_matching: false,
	};

	// ── filters section ──
	const $filters = $(frm.fields_dict.filters_html.wrapper);
	$filters.html(`
		<div class="se-filters" style="display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;margin-bottom:12px;">
			<div class="frappe-control" style="min-width:140px;">
				<label class="control-label">${__("Journal")}</label>
				<input class="form-control input-sm" data-filter="journal" placeholder="${__("AC, VT, BQ…")}">
			</div>
			<div class="frappe-control" style="min-width:100px;">
				<label class="control-label">${__("MVT")}</label>
				<input class="form-control input-sm" data-filter="mvt">
			</div>
			<div class="frappe-control" style="min-width:100px;">
				<label class="control-label">${__("N° Doc")}</label>
				<input class="form-control input-sm" data-filter="ref_doc">
			</div>
			<div class="frappe-control" style="min-width:120px;">
				<label class="control-label">${__("Date de")}</label>
				<input class="form-control input-sm" type="date" data-filter="date_from">
			</div>
			<div class="frappe-control" style="min-width:120px;">
				<label class="control-label">${__("Date à")}</label>
				<input class="form-control input-sm" type="date" data-filter="date_to">
			</div>
			<div class="frappe-control" style="min-width:120px;">
				<label class="control-label">${__("Compte")}</label>
				<input class="form-control input-sm" data-filter="compte">
			</div>
			<div class="frappe-control" style="min-width:120px;">
				<label class="control-label">${__("Libellé contient")}</label>
				<input class="form-control input-sm" data-filter="libelle">
			</div>
			<div class="frappe-control" style="min-width:130px;">
				<label class="control-label">${__("Type")}</label>
				<select class="form-control input-sm" data-filter="entry_type">
					<option value="">${__("Tous")}</option>
					<option value="Payable">${__("Payable")}</option>
					<option value="Receivable">${__("Receivable")}</option>
					<option value="Treasury">${__("Treasury")}</option>
					<option value="Declaration">${__("Declaration")}</option>
				</select>
			</div>
			<div class="frappe-control" style="min-width:120px;">
				<label class="control-label">${__("Origine")}</label>
				<select class="form-control input-sm" data-filter="origin">
					<option value="">${__("Tous")}</option>
					<option value="Imported">${__("Importé")}</option>
					<option value="Saisie">${__("Saisie")}</option>
				</select>
			</div>
			<button class="btn btn-primary btn-sm se-search-btn" style="height:30px;">${__("Rechercher")}</button>
		</div>
	`);

	// ── toolbar ──
	const $toolbar = $(frm.fields_dict.toolbar_html.wrapper);
	$toolbar.html(`
		<div class="se-toolbar" style="display:flex;gap:8px;align-items:center;margin-bottom:12px;">
			<span class="se-selection-info text-muted" style="flex:1;"></span>
			<button class="btn btn-danger btn-sm se-delete-selected-btn" disabled>
				${__("Supprimer la sélection")}
			</button>
			<button class="btn btn-danger btn-sm se-delete-all-btn">
				${__("Tout supprimer")}
			</button>
		</div>
	`);

	// ── results ──
	const $results = $(frm.fields_dict.results_html.wrapper);
	$results.html(`
		<div class="se-results">
			<div class="se-table-wrapper" style="overflow-x:auto;"></div>
			<div class="se-pager" style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
				<span class="se-pager-info text-muted"></span>
				<div>
					<button class="btn btn-default btn-xs se-prev-btn">${__("Précédent")}</button>
					<button class="btn btn-default btn-xs se-next-btn">${__("Suivant")}</button>
				</div>
			</div>
		</div>
	`);

	// ── helpers ──
	function esc(s) { return frappe.utils.escape_html(s || ""); }

	function gather_filters() {
		const f = {};
		$filters.find("[data-filter]").each(function () {
			const v = $(this).val();
			const k = $(this).data("filter");
			if (v) f[k] = v;
		});
		return f;
	}

	function selection_key(row) { return `${row.doctype}::${row.name}`; }

	function update_selection_ui() {
		const count = state.select_all_matching ? state.total : state.selected.size;
		const $info = $toolbar.find(".se-selection-info");
		if (count > 0) {
			const label = state.select_all_matching
				? __("{0} écritures correspondantes sélectionnées", [state.total])
				: __("{0} sélectionnée(s)", [count]);
			$info.html(label);
		} else {
			$info.html("");
		}
		$toolbar.find(".se-delete-selected-btn").prop("disabled", count === 0);
	}

	function render_table() {
		const rows = state.rows;
		const all_checked = rows.length > 0 && rows.every(r => state.selected.has(selection_key(r)));

		let html = `<table class="table table-bordered table-hover table-sm" style="font-size:12px;">
			<thead><tr>
				<th style="width:30px;"><input type="checkbox" class="se-select-all-page" ${all_checked ? "checked" : ""}></th>
				<th>${__("MVT")}</th>
				<th>${__("Journal")}</th>
				<th>${__("Date")}</th>
				<th>${__("Libellé")}</th>
				<th>${__("Réf")}</th>
				<th style="text-align:right;">${__("Débit")}</th>
				<th style="text-align:right;">${__("Crédit")}</th>
				<th>${__("Type")}</th>
				<th>${__("Import")}</th>
				<th>${__("Lettré")}</th>
			</tr></thead><tbody>`;

		if (rows.length === 0) {
			html += `<tr><td colspan="11" class="text-center text-muted">${__("Aucun résultat")}</td></tr>`;
		}
		for (const row of rows) {
			const key = selection_key(row);
			const checked = state.selected.has(key) ? "checked" : "";
			html += `<tr data-key="${esc(key)}" data-name="${esc(row.name)}" data-doctype="${esc(row.doctype)}">
				<td><input type="checkbox" class="se-row-check" ${checked}></td>
				<td>${esc(row.mvt)}</td>
				<td>${esc(row.journal)}</td>
				<td>${esc(row.date_operation)}</td>
				<td>${esc(row.libelle)}</td>
				<td>${esc(row.ref_doc)}</td>
				<td style="text-align:right;">${frappe.format(row.total_debit, {fieldtype: "Currency"})}</td>
				<td style="text-align:right;">${frappe.format(row.total_credit, {fieldtype: "Currency"})}</td>
				<td>${esc(row.entry_type)}</td>
				<td>${row.imported ? "✓" : ""}</td>
				<td>${row.has_lettered ? '<span class="indicator-pill red">' + __("Oui") + '</span>' : ""}</td>
			</tr>`;
		}
		html += "</tbody></table>";

		if (state.total > state.page_size && !state.select_all_matching) {
			html += `<div class="text-center" style="margin-top:4px;">
				<a href="#" class="se-select-all-matching">${
					__("Sélectionner les {0} écritures correspondantes", [state.total])
				}</a>
			</div>`;
		}

		const $wrapper = $results.find(".se-table-wrapper");
		$wrapper.html(html);

		// pager info
		const from_ = state.total ? (state.page - 1) * state.page_size + 1 : 0;
		const to_ = Math.min(state.page * state.page_size, state.total);
		$results.find(".se-pager-info").text(
			state.total ? `${from_}–${to_} / ${state.total}` : ""
		);
		$results.find(".se-prev-btn").prop("disabled", state.page <= 1);
		$results.find(".se-next-btn").prop("disabled", to_ >= state.total);
	}

	function do_search(page) {
		state.page = page || 1;
		state.select_all_matching = false;
		const filters = gather_filters();
		frappe.call({
			method: "erpnext.custom_modules.organization.suppression_ecritures_api.search_transactions",
			args: { filters: JSON.stringify(filters), page: state.page, page_size: state.page_size },
			freeze: true,
			callback(r) {
				state.rows = r.message.rows || [];
				state.total = r.message.total || 0;
				render_table();
				update_selection_ui();
			},
		});
	}

	// ── delete confirm dialog ──
	function show_confirm_dialog(info, is_select_all, filters) {
		const is_sys = frappe.user_roles.includes("System Manager");
		let desc = `<p><strong>${__("Écritures à supprimer:")}</strong></p><ul>`;
		for (const [type, count] of Object.entries(info.counts || {})) {
			if (count) desc += `<li>${esc(type)}: ${count}</li>`;
		}
		desc += `</ul><p>${__("Total")}: <strong>${info.total}</strong></p>`;
		if (info.lettered) {
			desc += `<p class="text-warning">${
				__("{0} écritures lettrées/pointées seront ignorées", [info.lettered])
			}${is_sys ? __(", sauf si vous cochez Forcer.") : "."}</p>`;
		}
		desc += `<p>${__("Tapez <b>SUPPRIMER</b> pour confirmer:")}</p>`;

		const fields = [
			{ fieldtype: "HTML", options: desc },
			{ fieldname: "confirm_text", fieldtype: "Data", label: __("Confirmation"), reqd: 1 },
		];
		if (is_sys && info.lettered) {
			fields.push({
				fieldname: "force",
				fieldtype: "Check",
				label: __("Forcer (supprimer même les écritures lettrées/pointées)"),
			});
		}

		const d = new frappe.ui.Dialog({
			title: __("Confirmer la suppression"),
			fields: fields,
			primary_action_label: __("Supprimer"),
			primary_action(values) {
				if (values.confirm_text !== "SUPPRIMER") {
					frappe.msgprint(__("Tapez exactement SUPPRIMER pour confirmer."));
					return;
				}
				d.hide();
				const args = {
					force: values.force ? 1 : 0,
				};
				if (is_select_all || state.select_all_matching) {
					args.filters = JSON.stringify(filters);
					args.select_all = 1;
				} else {
					args.names = JSON.stringify(
						Array.from(state.selected.values())
					);
				}
				frappe.call({
					method: "erpnext.custom_modules.organization.suppression_ecritures_api.delete_transactions",
					args: args,
					freeze: true,
					freeze_message: __("Suppression en cours…"),
					callback(r) {
						const res = r.message || {};
						if (res.enqueued) {
							frappe.show_alert({
								message: __("Suppression de {0} écritures lancée en arrière-plan.", [res.count]),
								indicator: "blue",
							});
						} else {
							frappe.show_alert({
								message: __(
									"{0} supprimées, {1} ignorées (lettrées), {2} échouées",
									[res.deleted, res.skipped, res.failed]
								),
								indicator: res.deleted ? "green" : "orange",
							}, 10);
						}
						state.selected.clear();
						state.select_all_matching = false;
						do_search(1);
					},
				});
			},
		});
		d.show();
	}

	function confirm_delete(targets_or_all, filters) {
		const is_select_all = targets_or_all === "all";
		if (!is_select_all && !state.select_all_matching) {
			const counts = {};
			let lettered = 0;
			for (const item of state.selected.values()) {
				const t = item.entry_type || item.doctype;
				counts[t] = (counts[t] || 0) + 1;
				if (item.has_lettered) lettered += 1;
			}
			show_confirm_dialog({ counts, total: state.selected.size, lettered }, false, filters);
			return;
		}

		frappe.call({
			method: "erpnext.custom_modules.organization.suppression_ecritures_api.count_transactions",
			args: { filters: JSON.stringify(filters) },
			freeze: true,
			callback(r) {
				show_confirm_dialog(r.message, is_select_all, filters);
			},
		});
	}

	// ── events ──
	$filters.find(".se-search-btn").on("click", () => {
		state.selected.clear();
		do_search(1);
	});

	$results.on("change", ".se-select-all-page", function () {
		const checked = this.checked;
		state.rows.forEach(r => {
			const key = selection_key(r);
			if (checked) {
				state.selected.set(key, {
					name: r.name,
					doctype: r.doctype,
					journal: r.journal,
					mvt: r.mvt,
					entry_type: r.entry_type,
					has_lettered: r.has_lettered,
				});
			} else {
				state.selected.delete(key);
				state.select_all_matching = false;
			}
		});
		render_table();
		update_selection_ui();
	});

	$results.on("change", ".se-row-check", function () {
		const $tr = $(this).closest("tr");
		const key = $tr.data("key");
		if (this.checked) {
			const row = state.rows.find(r => selection_key(r) === key) || {
				name: $tr.data("name"),
				doctype: $tr.data("doctype"),
			};
			state.selected.set(key, {
				name: row.name,
				doctype: row.doctype,
				journal: row.journal,
				mvt: row.mvt,
				entry_type: row.entry_type,
				has_lettered: row.has_lettered,
			});
		} else {
			state.selected.delete(key);
			state.select_all_matching = false;
		}
		update_selection_ui();
	});

	$results.on("click", ".se-select-all-matching", function (e) {
		e.preventDefault();
		state.select_all_matching = true;
		// also select all on current page visually
		state.rows.forEach(r => {
			state.selected.set(selection_key(r), { name: r.name, doctype: r.doctype });
		});
		render_table();
		update_selection_ui();
	});

	$results.find(".se-prev-btn").on("click", () => {
		if (state.page > 1) do_search(state.page - 1);
	});
	$results.find(".se-next-btn").on("click", () => {
		if (state.page * state.page_size < state.total) do_search(state.page + 1);
	});

	$toolbar.find(".se-delete-selected-btn").on("click", () => {
		const filters = gather_filters();
		confirm_delete("selected", filters);
	});

	$toolbar.find(".se-delete-all-btn").on("click", () => {
		const filters = gather_filters();
		confirm_delete("all", filters);
	});

	// initial search
	do_search(1);
}
