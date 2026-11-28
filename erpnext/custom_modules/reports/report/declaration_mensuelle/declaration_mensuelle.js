// Declaration Mensuelle — the Reports section's recap of the monthly
// declarations. Four views toggle at the top (like Ledger Data's views):
// RECAP (the native script-report grid, default), TABLEAU DE BORD (cards +
// charts), FICHE MOIS (one month's rubriques, controls and actions) and
// Vue XLSX (the Mensuelle sheet_file in the bundled Sheets editor, shared
// handshake via erpnext.reports.mount_sheets_editor). The Entreprise and
// Exercice always come from the dock context — no filter for them.
const DM_VIEW_TITLES = ["Recap", "Tableau de bord", "Fiche mois", "Vue XLSX"];
const DM_MONTHS = ["01","02","03","04","05","06","07","08","09","10","11","12"];
const DM_MONTH_NAMES = ["Janvier","Fevrier","Mars","Avril","Mai","Juin","Juillet","Aout","Septembre","Octobre","Novembre","Decembre"];

frappe.query_reports["Declaration Mensuelle"] = {
	filters: [
		{
			fieldname: "source",
			label: __("Source"),
			fieldtype: "Select",
			options: "Calculé\nDéclaré\nLiquidé\nÉcarts",
			default: "Calculé",
			reqd: 1,
		},
		{
			fieldname: "mois",
			label: __("Mois"),
			fieldtype: "Select",
			options: "\n01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
			default: "",
		},
	],
	onload(report) {
		setup_declaration_views(report);
		// this frappe version knows no settings.refresh hook: every native
		// render re-decorates the Écarts cells and re-renders the active
		// custom view (the settings object is the shared JS global, so the
		// wrap happens once per page load)
		const settings = frappe.query_reports["Declaration Mensuelle"];
		if (!settings.__dm_after_render_hooked) {
			settings.__dm_after_render_hooked = true;
			const previous_after_render = report.report_settings.after_datatable_render;
			report.report_settings.after_datatable_render = (datatable) => {
				if (previous_after_render) previous_after_render(datatable);
				decorate_declaration_ecarts(report);
				render_declaration_view(report);
			};
		}
	},
};

// ── data ─────────────────────────────────────────────────────────────────────

function fetch_declaration_data(report) {
	frappe
		.call({
			type: "GET",
			method:
				"erpnext.custom_modules.reports.report.declaration_mensuelle.get_declaration_report_data",
		})
		.then((r) => {
			report.__dm_data = r.message || {};
			render_declaration_view(report);
		})
		.catch(() => {
			report.__dm_data = null;
		});
}

// ── the view toggle + containers ─────────────────────────────────────────────

function setup_declaration_views(report) {
	// refresh_report wipes custom_actions before onload: the switcher is
	// rebuilt on every pass; the containers and the fetched data live on the
	// report object and survive
	report.__dm_view = report.__dm_view || "recap";

	const actions = report.page.custom_actions.length
		? report.page.custom_actions
		: report.page.custom_mobile_actions;
	const $group = $(`<div class="custom-btn-group dm-view-switcher"></div>`);
	DM_VIEW_TITLES.forEach((label, index) => {
		const view = ["recap", "dashboard", "fiche", "xlsx"][index];
		const $btn = $(`<button type="button" class="btn btn-default btn-sm dm-view-btn" data-view="${view}">${__(
			label
		)}</button>`);
		$btn.on("click", () => set_declaration_view(report, view));
		$group.append($btn);
	});
	actions.removeClass("hide").find(".dm-view-switcher").remove();
	actions.addClass("hide").append($group);

	if (!report.__dm_container) {
		// the custom views render into their own container over page.main;
		// the RECAP is the report's native datatable
		const container = $(`<div class="dm-view-container" style="display: none;"></div>`);
		report.page.main.append(container);
		report.__dm_container = container;
	}
	set_declaration_view(report, report.__dm_view);
	fetch_declaration_data(report);
}

function set_declaration_view(report, view) {
	report.__dm_view = view;
	const $buttons = report.page.custom_actions.find(".dm-view-btn");
	$buttons.each(function () {
		$(this).toggleClass("btn-primary", $(this).attr("data-view") === view);
	});
	render_declaration_view(report);
}

function render_declaration_view(report) {
	if (!report.__dm_views_ready) return;
	const view = report.__dm_view || "recap";
	const container = report.__dm_container;
	const show_native = view === "recap";
	if (show_native) {
		container.hide();
		report.$report.show();
	} else {
		report.$report.hide();
		container.show();
	}
	if (!report.__dm_data) return; // the fetch's .then renders when ready
	if (view === "dashboard") render_dm_dashboard(report, container);
	else if (view === "fiche") render_dm_fiche(report, container);
	else if (view === "xlsx") render_dm_xlsx(report, container);
}

// ── RECAP helpers ────────────────────────────────────────────────────────────

// out-of-tolerance écart cells highlight in the native datatable (the Écarts
// source): rows carry .dt-row-{index}, columns .dt-cell--col-{index}
const DM_ECART_STYLES = `
	.dt-cell.dm-ecart-alert { background-color: rgba(206, 44, 44, 0.14) !important; font-weight: 600; }
`;
let dm_ecart_styles_injected = false;

function decorate_declaration_ecarts(report) {
	try {
		const source = report.get_filter_value("source") || "Calcule";
		if (source !== "Ecarts" && source !== "Écarts") return;
		if (!report.datatable || !report.__dm_data) return;
		if (!dm_ecart_styles_injected) {
			$("<style>").text(DM_ECART_STYLES).appendTo("head");
			dm_ecart_styles_injected = true;
		}
		const rows = report.__dm_data.recap.rows.ecarts;
		const wrapper = report.datatable.wrapper || report.$report;
		rows.forEach((row, index) => {
			const out = row.out_of_tolerance || [];
			if (!out.length) return;
			const keys = report.__dm_data.recap.columns.map((column) => column.key);
			const $cells = wrapper.find(`.dt-row-${index}`);
			out.forEach((key) => {
				const colIndex = keys.indexOf(key);
				if (colIndex >= 0) $cells.find(`.dt-cell--col-${colIndex}`).addClass("dm-ecart-alert");
			});
		});
	} catch (error) {
		// highlighting is cosmetic: never break the report
	}
}

// ── shared rendering helpers ─────────────────────────────────────────────────

function dm_money(value) {
	return (value || 0).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}

function dm_month_label(month) {
	const name = DM_MONTH_NAMES[(parseInt(month, 10) || 1) - 1] || "";
	return `${name} ${frappe.boot.axeane_context?.exercice_label || ""}`.trim() || month;
}

function dm_fiche_month(report) {
	const value = report.get_filter_value("mois");
	if (value) return value;
	// default: the latest month that carries a Mensuelle or a computed DM
	const data = report.__dm_data;
	if (!data) return "";
	const with_data = [];
	[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].forEach((month) => {
		if (data.details.calcule[month] || data.details.declare[month]) with_data.push(month);
	});
	return with_data.length ? DM_MONTHS[with_data[with_data.length - 1] - 1] : "";
}

// ── TABLEAU DE BORD ──────────────────────────────────────────────────────────

function render_dm_dashboard(report, container) {
	const data = report.__dm_data;
	const dashboard = data.dashboard || {};
	container.html(`
		<div class="dm-dashboard" style="padding: 15px; overflow: auto; height: 100%;">
			<div class="dm-cards" style="display:flex;flex-wrap:wrap;gap:12px;"></div>
			<div class="dm-chart" id="dm-chart-tva" style="margin-top: 20px;"></div>
			<div class="dm-chart" id="dm-chart-composition" style="margin-top: 20px;"></div>
			<div class="dm-chart" id="dm-chart-total" style="margin-top: 20px;"></div>
		</div>`);

	const card = (label, value, color, sub) => `
		<div style="background:${color};border:1px solid var(--border-color,#d1d8dd);border-radius:6px;padding:10px 16px;min-width:170px;">
			<div style="font-size:11px;color:#6b7280;text-transform:uppercase;">${label}</div>
			<div style="font-size:18px;font-weight:700;">${sub || dm_money(value)}</div>
		</div>`;
	container
		.find(".dm-cards")
		.html(
			card(__("Total à payer cumulé (Calculé)"), dashboard.total_a_payer_cumule, "#fff7e6") +
				card(__("Total à payer cumulé (Déclaré)"), dashboard.total_a_payer_cumule_declare, "#fff7e6") +
				card(__("TVA nette cumulée"), dashboard.tva_nette_cumulee, "#eef4fb") +
				card(__("RS cumulés"), dashboard.rs_cumules, "#eef6ee") +
				card(__("Mois déposés / clôturés / à faire"), null, "#f7f7f7",
					`${dashboard.months_depose} / ${dashboard.months_cloture} / ${dashboard.months_a_faire}`) +
				card(__("Mois avec écarts"), dashboard.months_with_ecarts_count, "#fdf2f2")
		);

	const labels = DM_MONTHS;
	const calcule = data.recap.rows.calcule;
	const declare = data.recap.rows.declare;
	const liquide = data.recap.rows.liquide;
	const num = (row, key) => row[key] || 0;

	render_dm_chart("dm-chart-tva", __("TVA par mois"), "line", labels, [
		{ name: __("TVA collectée"), values: calcule.map((row) => num(row, "tva7") + num(row, "tva19")) },
		{ name: __("TVA déductible"), values: calcule.map((row) => num(row, "tva_deductible")) },
		{ name: __("TVA à payer"), values: calcule.map((row) => num(row, "tva_a_payer")) },
	]);
	render_dm_chart("dm-chart-composition", __("Composition du total à payer"), "bar", labels, [
		{ name: __("RS"), values: calcule.map((row) => num(row, "irpp") + num(row, "css") + num(row, "rs1") + num(row, "rs3") + num(row, "rs_loyer")) },
		{ name: __("TFP"), values: calcule.map((row) => num(row, "tfp")) },
		{ name: __("FOPROLOS"), values: calcule.map((row) => num(row, "foprolos")) },
		{ name: __("TVA"), values: calcule.map((row) => num(row, "tva_a_payer")) },
		{ name: __("Timbre"), values: calcule.map((row) => num(row, "timbre")) },
		{ name: __("TCL"), values: calcule.map((row) => num(row, "tcl")) },
	], true);
	render_dm_chart("dm-chart-total", __("Total calculé vs déclaré vs liquidé"), "line", labels, [
		{ name: __("Total calculé"), values: calcule.map((row) => num(row, "total")) },
		{ name: __("Total déclaré"), values: declare.map((row) => num(row, "total")) },
		{ name: __("Total liquidé"), values: liquide.map((row) => num(row, "total")) },
	]);
}

function render_dm_chart(anchor, title, type, labels, datasets, stacked) {
	const el = document.getElementById(anchor);
	if (!el || typeof frappe.Chart === "undefined") return;
	el.innerHTML = `<div style="font-weight:600;margin-bottom:4px;">${frappe.utils.escape_html(title)}</div>
		<div class="dm-chart-canvas" style="height: 280px;"></div>`;
	new frappe.Chart(el.querySelector(".dm-chart-canvas"), {
		title: "",
		type,
		data: { labels, datasets },
		height: 260,
		barOptions: { stacked: Boolean(stacked) },
		lineOptions: { regionFill: 0 },
		axisOptions: { xIsSeries: false, shortestBar: 2 },
	});
}

// ── FICHE MOIS ───────────────────────────────────────────────────────────────

function render_dm_fiche(report, container) {
	const data = report.__dm_data;
	const month = dm_fiche_month(report);
	const calcule = (data.details.calcule || {})[month] || null;
	const declare = (data.details.declare || {})[month] || null;
	const esc = frappe.utils.escape_html;

	// the rubrique rows: the union of the DM lines and the declared lignes
	const rows_map = {};
	(calcule && calcule.lines ? calcule.lines : []).forEach((line) => {
		rows_map[line.code] = {
			code: line.code,
			libelle: line.libelle || "",
			brut: line.montant_brut,
			retenu: line.retenu,
		};
	});
	(declare && declare.lignes ? declare.lignes : []).forEach((line) => {
		const row = rows_map[line.code_rubrique] || (rows_map[line.code_rubrique] = { code: line.code_rubrique, libelle: "", brut: null, retenu: null });
		row.base_declaree = line.base_declaree;
		row.montant_declare = line.montant_declare;
		if (!row.libelle && line.code_rubrique) row.libelle = "";
	});
	const codes = Object.keys(rows_map).sort((a, b) => {
		const order = (code) => (code === "TOTAL" ? 999 : parseInt(code.replace(/[^0-9]/g, ""), 10) || 0);
		return order(a) - order(b);
	});
	const ecart_of = (row) =>
		row.montant_declare != null && row.retenu != null ? row.montant_declare - row.retenu : null;

	const body_rows = codes
		.map((code) => {
			const row = rows_map[code];
			const ecart = ecart_of(row);
			const out = ecart != null && Math.abs(ecart) > (data.recap.ecart_tolerance || 0.005);
			return `<tr>
				<td>${esc(code)}</td>
				<td>${esc(row.libelle || "")}</td>
				<td style="text-align:right;">${row.base_declaree != null ? dm_money(row.base_declaree) : "—"}</td>
				<td style="text-align:right;">${row.montant_declare != null ? dm_money(row.montant_declare) : "—"}</td>
				<td style="text-align:right;">${row.brut != null ? dm_money(row.brut) : "—"}</td>
				<td style="text-align:right;">${row.retenu != null ? dm_money(row.retenu) : "—"}</td>
				<td style="text-align:right;${out ? "color:#ce2c2c;font-weight:600;" : ""}">${
					ecart != null ? dm_money(ecart) : "—"
				}</td>
			</tr>`;
		})
		.join("");

	const controles = (declare && declare.controles ? declare.controles : [])
		.map(
			(control) => `<tr class="dm-controle-row dm-severity-${esc(control.severity || "Info")}">
				<td>${esc(control.check_code || "")}</td>
				<td>${esc(control.severity || "")}</td>
				<td>${esc(control.message || "")}</td>
				<td style="text-align:right;">${control.declare != null ? dm_money(control.declare) : "—"}</td>
				<td style="text-align:right;">${control.attendu != null ? dm_money(control.attendu) : "—"}</td>
				<td style="text-align:right;">${control.ecart != null ? dm_money(control.ecart) : "—"}</td>
			</tr>`
		)
		.join("");

	const month_options = DM_MONTHS.map(
		(m) => `<option value="${m}" ${m === month ? "selected" : ""}>${m}</option>`
	).join("");

	container.html(`
		<div class="dm-fiche" style="padding: 15px; overflow: auto; height: 100%;">
			<div class="dm-fiche-head" style="display:flex;align-items:center;gap:14px;margin-bottom:14px;">
				<label style="font-weight:600;">${__("Mois")}</label>
				<select class="form-control input-sm dm-fiche-month" style="width: 90px;">${month_options}</select>
				<div style="display:flex;gap:8px;flex-wrap:wrap;">
					<button class="btn btn-sm btn-primary dm-open-entries">${__("Ouvrir la déclaration (Entries)")}</button>
					<button class="btn btn-sm btn-default dm-open-facturation">${__("Ouvrir le document (Facturation)")}</button>
					<button class="btn btn-sm btn-default dm-open-xlsx">${__("Vue XLSX")}</button>
				</div>
			</div>
			<div class="dm-fiche-meta" style="margin-bottom: 14px; color:#6b7280; font-size:12px;"></div>
			<div style="font-weight:600;margin-bottom:6px;">${__("Rubriques")}</div>
			<table class="table table-bordered" style="margin-bottom: 18px;">
				<thead><tr>
					<th>${__("Code")}</th><th>${__("Libelle")}</th>
					<th style="text-align:right;">${__("Base déclarée")}</th>
					<th style="text-align:right;">${__("Montant déclaré")}</th>
					<th style="text-align:right;">${__("Brut calculé")}</th>
					<th style="text-align:right;">${__("Retenu calculé")}</th>
					<th style="text-align:right;">${__("Écart")}</th>
				</tr></thead>
				<tbody>${body_rows || `<tr><td colspan="7">${__("Aucune rubrique.")}</td></tr>`}</tbody>
			</table>
			<div style="font-weight:600;margin-bottom:6px;">${__("Contrôles")}</div>
			<table class="table table-bordered dm-controles-table">
				<thead><tr>
					<th>${__("Controle")}</th><th>${__("Gravité")}</th><th>${__("Message")}</th>
					<th style="text-align:right;">${__("Declaré")}</th>
					<th style="text-align:right;">${__("Attendu")}</th>
					<th style="text-align:right;">${__("Ecart")}</th>
				</tr></thead>
				<tbody>${controles || `<tr><td colspan="6">${__("Aucun contrôle exécuté — lancez Vérifier sur la Mensuelle.")}</td></tr>`}</tbody>
			</table>
		</div>`);

	container.find(".dm-fiche-month").on("change", function () {
		report.set_filter_value("mois", this.value);
		render_dm_fiche(report, container);
	});
	container.find(".dm-open-entries").on("click", () => {
		if (declare && declare.name) {
			erpnext.facturation.open_entry("Mensuelle", declare.name);
		} else {
			frappe.msgprint({
				message: __("Aucune Mensuelle pour ce mois: la déclaration se calcule depuis le grand livre."),
				indicator: "orange",
			});
		}
	});
	container.find(".dm-open-facturation").on("click", () => {
		if (declare && declare.name) frappe.set_route("Form", "Mensuelle", declare.name);
		else
			frappe.msgprint({
				message: __("Aucun document Mensuelle pour ce mois."),
				indicator: "orange",
			});
	});
	container.find(".dm-open-xlsx").on("click", () => {
		set_declaration_view(report, "xlsx");
	});

	const meta = [];
	if (calcule && calcule.name) meta.push(__("Declaration (Entries): {0} ({1})", [calcule.name, calcule.status]));
	const portal = (data.portal || {})[month];
	if (portal && portal.numero_declaration) {
		meta.push(__("Recu portail: {0} — liquidé {1}", [portal.numero_declaration, dm_money(portal.montant_liquide)]));
	}
	if (declare && declare.name) meta.push(__("Mensuelle: {0} — contrôle {1}", [declare.name, declare.check_status]));
	if (calcule && calcule.name) {
		const label = frappe.utils.escape_html(__("Ouvrir la Declaration Transaction"));
		meta.push(frappe.utils.get_form_link("Declaration Transaction", calcule.name, true, label));
	}
	container.find(".dm-fiche-meta").html(meta.join(" &nbsp;—&nbsp; "));
}

// ── Vue XLSX ─────────────────────────────────────────────────────────────────

function render_dm_xlsx(report, container) {
	const data = report.__dm_data;
	const month = dm_fiche_month(report);
	const declare = (data.details.declare || {})[month] || null;

	if (report.__dm_xlsx_cleanup) {
		report.__dm_xlsx_cleanup();
		report.__dm_xlsx_cleanup = null;
	}
	const wrapper = `<div class="dm-xlsx" style="height: 100%; position: relative;">
		<div class="dm-xlsx-head" style="position:absolute;top:8px;left:16px;z-index:5;">
			<button class="btn btn-sm btn-default dm-back-fiche">${__("← Fiche mois")}</button>
		</div>
		<div class="dm-xlsx-frame" style="height: 100%;"></div>
	</div>`;
	container.html(wrapper);
	container.find(".dm-back-fiche").on("click", () => set_declaration_view(report, "fiche"));

	const frame = container.find(".dm-xlsx-frame")[0];
	if (!declare || !declare.sheet_file) {
		frame.innerHTML = `<div class="alert alert-warning" style="margin: 40px auto; max-width: 480px;">
			${__("Aucune feuille importée")}</div>`;
		return;
	}
	if (!declare.sheet_file_docname) {
		frame.innerHTML = `<div class="alert alert-warning" style="margin: 40px auto; max-width: 480px;">
			${__("Le fichier de la feuille est introuvable.")}</div>`;
		return;
	}
	// the bundled GenOffice Sheets editor over the SHARED handshake; the
	// listener's cleanup rides the report object so a view switch unmounts it
	report.__dm_xlsx_cleanup = erpnext.reports.mount_sheets_editor(frame, declare.sheet_file_docname, {
		title: __("Mensuelle XLSX"),
	});
}
