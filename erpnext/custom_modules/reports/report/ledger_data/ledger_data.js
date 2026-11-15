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

frappe.query_reports["Ledger Data"] = {
	filters: [
		{
			fieldname: "ledger_type",
			label: __("Type grand livre"),
			fieldtype: "Select",
			options: "General\nAuxiliaire Client\nAuxiliaire Fournisseur",
			default: "General",
			reqd: 1,
		},
		{
			fieldname: "journal",
			label: __("Code Journal"),
			fieldtype: "MultiSelectList",
			options: "Journal",
			get_data(txt) {
				return frappe.db.get_link_options("Journal", txt);
			},
		},
		{
			fieldname: "period_type",
			label: __("Periode"),
			fieldtype: "Select",
			options: "Mensuelle\nTrimestrielle\nAnnuelle\nPersonnalisee",
			default: "Mensuelle",
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Mois"),
			fieldtype: "Select",
			options: "Janvier\nFevrier\nMars\nAvril\nMai\nJuin\nJuillet\nAout\nSeptembre\nOctobre\nNovembre\nDecembre",
			default: "Janvier",
			reqd: 1,
			depends_on: "eval:doc.period_type == 'Mensuelle'",
		},
		{
			fieldname: "quarter",
			label: __("Trimestre"),
			fieldtype: "Select",
			options: "T1\nT2\nT3\nT4",
			default: "T1",
			depends_on: "eval:doc.period_type == 'Trimestrielle'",
		},
		{
			fieldname: "from_date",
			label: __("Du"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
		},
		{
			fieldname: "to_date",
			label: __("Au"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
		},
		{
			fieldname: "devise",
			label: __("Devise"),
			fieldtype: "Link",
			options: "Currency",
			default: "TND",
		},
		{
			fieldname: "lettrage",
			label: __("Lettrage"),
			fieldtype: "Select",
			options: "Tous\nLettre\nNon lettre",
			default: "Tous",
		},
		{
			fieldname: "extract_type",
			label: __("Type Extrait"),
			fieldtype: "Select",
			options: "Tous les comptes\nComptes mouvementes\nComptes non soldes",
			default: "Tous les comptes",
			reqd: 1,
		},
		{
			fieldname: "mvt",
			label: __("Piece comptable"),
			fieldtype: "Data",
			description: __("One or several MVT numbers, comma-separated"),
		},
	],

	// the PDF / XLSX mounts the switcher calls: el = the wide-open container,
	// filters = the CURRENT filter values (report.get_filter_values()). The
	// real previews are built later on this contract.
	views: {
		pdf: {
			mount(el, filters) {
				el.innerHTML = "";
				el.appendChild(
					frappe.ui.empty_state({
						icon: "file-text",
						title: __("Apercu PDF, bientot disponible"),
						description: __("The PDF preview will be generated from the XLSX view."),
					})
				);
			},
			unmount() {},
		},
		xlsx: {
			mount(el, filters) {
				el.innerHTML = "";
				el.appendChild(
					frappe.ui.empty_state({
						icon: "table",
						title: __("XLSX view, coming soon"),
						description: __("The XLSX view will be generated from the same data."),
					})
				);
			},
			unmount() {},
		},
	},

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
		return default_formatter(value);
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

		// the view switcher (PDF / List / XLSX) and the bottom summary bar
		// are shared with the Balance report (report_views.bundle.js): the
		// summary moves below the datatable in list view, the pdf / xlsx
		// placeholders mount with the current filter values, and a dock
		// context change re-runs the query and re-mounts the active view
		erpnext.reports.setup_views(report, {
			report_name: "Ledger Data",
			views: {
				pdf: {
					mount(el) {
						el.innerHTML = "";
						el.appendChild(
							frappe.ui.empty_state({
								icon: "file-text",
								title: __("Apercu PDF, bientot disponible"),
								description: __("The PDF preview will be generated from the XLSX view."),
							})
						);
					},
					unmount() {},
				},
				xlsx: {
					mount(el) {
						el.innerHTML = "";
						el.appendChild(
							frappe.ui.empty_state({
								icon: "table",
								title: __("XLSX view, coming soon"),
								description: __("The XLSX view will be generated from the same data."),
							})
						);
					},
					unmount() {},
				},
			},
		});

		setup_import_actions(report);
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
			// the freshly imported exercice reads best as a whole: Annuelle
			frappe.query_report.set_filter_value("period_type", "Annuelle");
			frappe.query_report.refresh();
		},
	});
}
