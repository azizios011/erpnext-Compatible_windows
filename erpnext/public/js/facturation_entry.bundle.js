// Entries-workspace entry point for the Facturation upload documents.
//
// The Facturation workspace only stores documents; the accounting entry for
// each one is produced later in the Entries workspace (stage 2). This file
// exposes erpnext.facturation.open_entry(doctype, name), which resolves the
// target entry doctype and either opens the already-linked entry or an
// UNSAVED new entry prefilled from the source document — nothing is
// auto-saved, the human reviews and saves. Registered globally through
// app_include_js; the per-row pen button of every Facturation list view and
// the "Saisie ecriture" form button both call it.
(function () {
	"use strict";

	var safe = function (fn) {
		try {
			return fn();
		} catch (error) {
			if (window.console && console.warn) {
				console.warn("facturation-entry:", error);
			}
			return null;
		}
	};

	window.erpnext = window.erpnext || {};
	erpnext.facturation = erpnext.facturation || {};

	erpnext.facturation.open_entry = function (doctype, name, mode) {
		// doctype/name identify the Facturation SOURCE; the entries resolver
		// resolves the entry doctype, the route and can_modify
		frappe.call({
			method: "erpnext.custom_modules.entries.api.open_entry",
			args: {
				source_doctype: doctype,
				source_name: name || "",
				mode: mode || "auto",
			},
			freeze: true,
			callback: function (r) {
				erpnext.facturation.navigate_open_entry(r.message);
			},
		});
	};

	erpnext.facturation.view_entry = function (entry_doctype, entry_name) {
		// "Voir l'ecriture": the linked entry in read-only inspect mode
		frappe.call({
			method: "erpnext.custom_modules.entries.api.open_entry",
			args: {
				entry_doctype: entry_doctype,
				name: entry_name || "",
				mode: "inspect",
			},
			freeze: true,
			callback: function (r) {
				erpnext.facturation.navigate_open_entry(r.message);
			},
		});
	};

	erpnext.facturation.navigate_open_entry = function (target) {
		if (!target || !target.route) {
			return;
		}
		if (target.kind === "form") {
			// Treasury / Declaration: the classic forms, exactly as before
			if (target.mode === "creation") {
				frappe.new_doc(target.entry_doctype, target.defaults || {});
			} else {
				frappe.set_route(...target.route);
			}
			return;
		}
		// kind "page": the trailing object becomes the query string the island
		// receives in props.query (creation only)
		const route = [...target.route];
		if (target.mode === "creation" && target.query && Object.keys(target.query).length) {
			frappe.set_route(...route, target.query);
		} else {
			frappe.set_route(...route);
		}
	};

	const FACTURATION_DOCTYPES = [
		"Facture Achat",
		"Releve Achat",
		"RS Achat",
		"Facture Vente",
		"RS Vente",
		"Releve Vente",
		"Releve Bancaire",
		"Remise de Cheque",
		"Versement Espece",
		"Mensuelle",
	];

	FACTURATION_DOCTYPES.forEach(function (doctype) {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				// the dock context the user is writing into ("MEDDEB · EX 2026")
				if (window.axeane && axeane.context && axeane.context.headline) {
					frm.dashboard.set_headline(frappe.utils.escape_html(axeane.context.headline()));
				}
				frm.add_custom_button(__("Saisie ecriture"), function () {
					erpnext.facturation.open_entry(frm.doctype, frm.doc.name);
				});
				if (frm.doc.entry && frm.doc.entry_doctype) {
					frm.add_custom_button(__("Voir l'ecriture"), function () {
						erpnext.facturation.view_entry(frm.doc.entry_doctype, frm.doc.entry);
					});
				}
			},
		});
	});

	// ── Facturation Print Format forms ────────────────────────────────────────
// The four "<Section> Print Format" doctypes opt into a sidebar visible on
// NEW records (generic frappe.form_sidebar.visible_on_new hook) and share
// one form handler: Validate / Preview on the CURRENT editor contents and
// the prompt dropdown next to the print icon.
const PRINT_FORMAT_DOCTYPES = [
	"Payable Print Format",
	"Receivable Print Format",
	"Treasury Print Format",
	"Declaration Print Format",
];

frappe.form_sidebar = frappe.form_sidebar || {};
frappe.form_sidebar.visible_on_new = function (frm) {
	return PRINT_FORMAT_DOCTYPES.indexOf(frm.doctype) !== -1;
};

function prompt_filename(category) {
	// mirrors the server-side filename rule: uppercased, spaces -> "_",
	// accents stripped, only A-Z 0-9 _ kept
	return (
		(category || "template")
			.normalize("NFD")
			.replace(/[\u0300-\u036f]/g, "")
			.toUpperCase()
			.replace(/ /g, "_")
			.replace(/[^A-Z0-9_]/g, "") + ".md"
	);
}

function call_print_format_api(method, args) {
	// quiet server calls: the rejection carries the server's message so the
	// caller can toast it (no msgprint dialog)
	return new Promise((resolve, reject) => {
		frappe.call({
			type: "POST",
			method: method,
			args: args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => {
				let message = null;
				try {
					const messages = JSON.parse((r && r._server_messages) || "[]");
					if (messages.length) {
						const first = typeof messages[0] === "string" ? JSON.parse(messages[0]) : messages[0];
						message = first.message || first;
					}
				} catch (e) {
					message = null;
				}
				reject(message || (r && r._error_message) || __("The request failed."));
			},
		});
	});
}

function prompt_error_toast(category) {
	const link = "/app/template-prompt/new?document_type=" + encodeURIComponent(category);
	frappe.show_alert({
		message:
			__("No enabled Template Prompt for {0}.", [category]) +
			' <a class="alert-link" href="' +
			link +
			'">' +
			__("Create it in Axeane Settings") +
			"</a>",
		indicator: "orange",
	});
}

function fetch_prompt(category) {
	return new Promise((resolve, reject) => {
		frappe.call({
			type: "GET",
			method: "frappe.custom_modules.axeane_settings.api.get_template_prompt",
			args: { document_type: category },
			silent: true,
			callback: (r) => resolve(r.message),
			error: () => reject(new Error("no prompt")),
		});
	});
}

function download_prompt(frm) {
	const category = frm.doc.category;
	fetch_prompt(category)
		.then((r) => {
			const blob = new Blob([r.content || ""], { type: "text/markdown" });
			const url = URL.createObjectURL(blob);
			const link = document.createElement("a");
			link.href = url;
			link.download = r.filename || prompt_filename(category);
			document.body.appendChild(link);
			link.click();
			link.remove();
			URL.revokeObjectURL(url);
		})
		.catch(() => prompt_error_toast(category));
}

function copy_prompt(frm) {
	fetch_prompt(frm.doc.category)
		.then((r) => {
			navigator.clipboard.writeText(r.content || "").then(() => {
				frappe.show_alert({
					message: __("Prompt copied to the clipboard."),
					indicator: "green",
				});
			});
		})
		.catch(() => prompt_error_toast(frm.doc.category));
}

function add_prompt_dropdown(frm) {
	const sidebar = frm.sidebar && frm.sidebar.sidebar;
	if (!sidebar || sidebar.find(".template-prompt-btn").length) return;
	const btn = frm.page.add_action_icon("file-text", () => {}, "", __("Template prompt"));
	btn.addClass("template-prompt-btn");
	btn.css("background-color", "transparent");
	// right next to the print icon in the sidebar title row
	sidebar.find(".form-print").append(btn);
	new frappe.ui.Dropdown({
		trigger: btn,
		align: "end",
		options: () => [
			{
				label: __("Download {0}", [prompt_filename(frm.doc.category)]),
				icon: "download",
				onclick: () => download_prompt(frm),
			},
			{
				label: __("Copy prompt"),
				icon: "copy",
				onclick: () => copy_prompt(frm),
			},
		],
	});
}

function print_format_args(frm) {
	return {
		template: frm.doc.name && !frm.doc.__islocal ? frm.doc.name : "",
		template_doctype: frm.doctype,
		category: frm.doc.category || "",
		editor_mode: frm.doc.editor_mode || "HTML/CSS",
		html_code: frm.doc.html_code || "",
		css_code: frm.doc.css_code || "",
		python_code: frm.doc.python_code || "",
	};
}

function run_print_format_action(frm, method) {
	if (!frm.doc.category) {
		frappe.show_alert({ message: __("Select a Category first."), indicator: "orange" });
		return;
	}
	call_print_format_api(method, print_format_args(frm))
		.then((r) => {
			if (method.indexOf("validate_print_format") !== -1) {
				frm.set_value("validation_status", r.status);
				frm.set_value("validation_log", r.log);
				frm.set_value("extraction_schema", r.schema);
				frm.set_value("validated_hash", r.validated_hash);
				frm.set_value("validated_on", r.validated_on);
				frappe.show_alert({
					message: r.status,
					indicator: r.status === "Failed" ? "red" : "green",
				});
			} else if (r && r.file_url) {
				window.open(r.file_url, "_blank");
			}
		})
		.catch((message) => {
			// e.g. "No validator for Facture Achat yet."
			frappe.show_alert({ message: message, indicator: "red" });
		});
}

erpnext.facturation.print_format_form = function (frm) {
	if (!frm.__print_format_buttons) {
		frm.__print_format_buttons = true;
		frm.add_custom_button(__("Validate"), () => {
			run_print_format_action(
				frm,
				"erpnext.custom_modules.facturation.print_format_api.validate_print_format"
			);
		});
		frm.add_custom_button(__("Preview"), () => {
			run_print_format_action(
				frm,
				"erpnext.custom_modules.facturation.print_format_api.preview_print_format"
			);
		});
	}
	add_prompt_dropdown(frm);
};
	// ── Facturation list views ───────────────────────────────────────────────────
// Every Facturation upload doctype shares one listview_settings factory
// (erpnext.facturation.list_settings). The top bar is reduced to the
// "Filtres Axeane" dialog button and the pen button is the engine's
// sanctioned settings.button (own column, delegated click). All list
// columns are real docfields rendered natively (Date transfert, Envoyé
// par, Type document, Nom fichier).

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

erpnext.facturation.party_field = function (doctype) {
	const df = (frappe.get_meta(doctype).fields || []).find(
		(df) => df.fieldtype === "Link" && ["Supplier", "Customer", "Bank Account"].includes(df.options)
	);
	return df ? df.fieldname : null;
};

/** Hide the standard toolbar pieces on Facturation lists: no ID search row,
 * no frappe Filter popover, no sort selector (the doctype JSON keeps
 * posting_date DESC). Called on load and again on every refresh — render
 * order can vary, and all three targets still exist on the current engine. */
function hide_standard_toolbar(listview) {
	listview.page.page_form.find(".standard-filter-section").addClass("hidden");
	if (listview.$filter_section) {
		listview.$filter_section.addClass("hidden");
	}
	if (listview.sort_selector && listview.sort_selector.wrapper) {
		listview.sort_selector.wrapper.addClass("hidden");
	}
}

/** The shared listview_settings for every Facturation upload doctype; the
 * per-doctype <doctype>_list.js files assign this factory's result. The pen
 * button is the engine's sanctioned settings.button — its own column and
 * delegated click instead of DOM injection — and refresh() re-applies the
 * toolbar hides after every render. Every step is guarded: our code can
 * never blank the rendered table. */
erpnext.facturation.list_settings = function (doctype) {
	return {
		add_fields: [
			"entry_status",
			"entry",
			"entry_doctype",
			"mvt",
			"attachment",
			"description",
		],
		hide_name_filter: true,
		get_indicator(doc) {
			if (doc.entry_status === "Comptabilisee") {
				return [__("Comptabilisee"), "green", "entry_status,=,Comptabilisee"];
			}
			if (doc.entry_status === "Brouillon") {
				return [__("Brouillon"), "orange", "entry_status,=,Brouillon"];
			}
			return [__("Non saisie"), "gray", "entry_status,=,Non saisie"];
		},
		onload(listview) {
			hide_standard_toolbar(listview);
			safe(function () {
				erpnext.facturation.setup_contenu_args(listview);
			});
			safe(function () {
				listview.page.add_inner_button(__("Filtres Axeane"), function () {
					safe(function () {
						erpnext.facturation.filter_panel(listview);
					});
				});
			});
		},
		refresh(listview) {
			hide_standard_toolbar(listview);
		},
		button: {
			get_label: () => frappe.utils.icon("square-pen", "xs"),
			get_description: () => __("Saisie ecriture"),
			show: () => true,
			action: (doc) => erpnext.facturation.open_entry(doctype, doc.name),
		},
	};
};

/** "Contenu" searches several fields at once; the list client only sends
 * ANDed filters, so the OR set is injected into the request args (the
 * reportview endpoint accepts or_filters). */
erpnext.facturation.setup_contenu_args = function (listview) {
	if (listview.__tu_contenu_patched) {
		return;
	}
	listview.__tu_contenu_patched = true;
	const original_get_args = listview.get_args.bind(listview);
	listview.get_args = function () {
		const args = original_get_args();
		if (listview._tu_contenu) {
			const like = "%" + listview._tu_contenu + "%";
			args.or_filters = [
				[listview.doctype, "reference_number", "like", like],
				[listview.doctype, "attachment", "like", like],
				[listview.doctype, "description", "like", like],
			];
			const party = erpnext.facturation.party_field(listview.doctype);
			if (party) {
				args.or_filters.push([listview.doctype, party, "like", like]);
			}
		}
		return args;
	};
};

erpnext.facturation.filter_panel = function (listview) {
	const doctype = listview.doctype;
	const party_field = erpnext.facturation.party_field(doctype);
	const party_df = party_field
		? (frappe.get_meta(doctype).fields || []).find((df) => df.fieldname === party_field)
		: null;

	const panel_fields = [
		{
			fieldname: "axeane_section",
			fieldtype: "Section Break",
			label: __("Validation Documents Comptables"),
		},
		{
			fieldname: "periode",
			fieldtype: "Select",
			label: __("Periode"),
			options: "Mensuelle\nTrimestrielle\nAnnuelle\nPersonnalisee",
			default: "Mensuelle",
		},
		{
			fieldname: "month",
			fieldtype: "Select",
			label: __("Mois"),
			options: GL_MONTHS.join("\n"),
			default: GL_MONTHS[new Date().getMonth()],
			depends_on: "eval:doc.periode == 'Mensuelle'",
		},
		{
			fieldname: "quarter",
			fieldtype: "Select",
			label: __("Trimestre"),
			options: "T1\nT2\nT3\nT4",
			default: "T1",
			depends_on: "eval:doc.periode == 'Trimestrielle'",
		},
		{
			fieldname: "du",
			fieldtype: "Date",
			label: __("Du"),
			depends_on: "eval:doc.periode == 'Personnalisee'",
		},
		{
			fieldname: "au",
			fieldtype: "Date",
			label: __("Au"),
			depends_on: "eval:doc.periode == 'Personnalisee'",
		},
		{ fieldname: "annee", fieldtype: "Data", label: __("Annee"), default: String(new Date().getFullYear()) },
		{ fieldname: "cb_panel_1", fieldtype: "Column Break" },
		{ fieldname: "contenu", fieldtype: "Data", label: __("Contenu"), description: __("Reference, party, file name, description") },
		{ fieldtype: "Section Break", label: __("Colonnes") },
		{ fieldname: "mvt", fieldtype: "Data", label: __("Piece") },
		{ fieldname: "attachment", fieldtype: "Data", label: __("Nom fichier") },
		{ fieldname: "cb_panel_2", fieldtype: "Column Break" },
		{ fieldname: "posting_from", fieldtype: "Date", label: __("Date piece du") },
		{ fieldname: "posting_to", fieldtype: "Date", label: __("Date piece au") },
		{ fieldname: "creation_from", fieldtype: "Date", label: __("Date transfert du") },
		{ fieldname: "creation_to", fieldtype: "Date", label: __("Date transfert au") },
		{ fieldname: "cb_panel_3", fieldtype: "Column Break" },
		{
			fieldname: "status",
			fieldtype: "Select",
			label: __("Statut"),
			options: "\nPending\nProcessed\nRejected",
		},
		{ fieldname: "owner_filter", fieldtype: "Link", options: "User", label: __("Envoye par") },
		{ fieldname: "description_filter", fieldtype: "Data", label: __("Description") },
		{
			fieldname: "ocr_status",
			fieldtype: "Select",
			label: __("S. OCR"),
			options: "\nNon traite\nEn cours\nTermine\nEchec",
		},
		{
			fieldname: "entry_status",
			fieldtype: "Select",
			label: __("S. Ecrit."),
			options: "\nNon saisie\nBrouillon\nComptabilisee",
		},
	];
	if (party_df) {
		panel_fields.push({
			fieldname: "party",
			fieldtype: "Link",
			options: party_df.options,
			label: party_df.label,
		});
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Validation Documents Comptables"),
		fields: panel_fields,
		primary_action_label: __("Afficher"),
		primary_action(values) {
			dialog.hide();
			erpnext.facturation.apply_filter_panel(listview, values || {});
		},
		secondary_action_label: __("Reinitialiser"),
		secondary_action() {
			dialog.hide();
			erpnext.facturation.reset_filter_panel(listview);
		},
	});

	erpnext.facturation.prefill_filter_panel(listview, dialog);
	dialog.show();
};

erpnext.facturation.filter_fieldnames = [
	"mvt",
	"attachment",
	"posting_date",
	"creation",
	"owner",
	"status",
	"description",
	"ocr_status",
	"entry_status",
];

erpnext.facturation.apply_filter_panel = function (listview, values) {
	const doctype = listview.doctype;
	const party_field = erpnext.facturation.party_field(doctype);
	const fields_in_use = erpnext.facturation.filter_fieldnames.concat(
		party_field ? [party_field] : []
	);

	// resolve the period first: Date piece wins over it when filled
	let from_date = null;
	let to_date = null;
	const year = parseInt(values.annee, 10) || new Date().getFullYear();
	const periode = values.periode || "Mensuelle";
	if (periode === "Personnalisee") {
		from_date = values.du ? frappe.datetime.str_to_obj(values.du) : null;
		to_date = values.au ? frappe.datetime.str_to_obj(values.au) : null;
	} else if (periode === "Trimestrielle") {
		const q = { T1: [0, 2], T2: [3, 5], T3: [6, 8], T4: [9, 11] }[values.quarter || "T1"];
		from_date = new Date(year, q[0], 1);
		to_date = new Date(year, q[1] + 1, 0);
	} else if (periode === "Annuelle") {
		from_date = new Date(year, 0, 1);
		to_date = new Date(year, 11, 31);
	} else {
		const m = GL_MONTHS.indexOf(values.month || GL_MONTHS[new Date().getMonth()]);
		from_date = new Date(year, m, 1);
		to_date = new Date(year, m + 1, 0);
	}
	if (values.posting_from) from_date = frappe.datetime.str_to_obj(values.posting_from);
	if (values.posting_to) to_date = frappe.datetime.str_to_obj(values.posting_to);

	const fmt = (d) => frappe.datetime.obj_to_user(d);

	const filters = [];
	if (from_date) filters.push([doctype, "posting_date", ">=", fmt(from_date)]);
	if (to_date) filters.push([doctype, "posting_date", "<=", fmt(to_date)]);
	if (values.mvt) filters.push([doctype, "mvt", "=", values.mvt]);
	if (values.attachment) filters.push([doctype, "attachment", "like", "%" + values.attachment + "%"]);
	if (values.creation_from) filters.push([doctype, "creation", ">=", fmt(frappe.datetime.str_to_obj(values.creation_from))]);
	if (values.creation_to) filters.push([doctype, "creation", "<=", fmt(frappe.datetime.str_to_obj(values.creation_to))]);
	if (values.status) filters.push([doctype, "status", "=", values.status]);
	if (values.owner_filter) filters.push([doctype, "owner", "=", values.owner_filter]);
	if (values.description_filter)
		filters.push([doctype, "description", "like", "%" + values.description_filter + "%"]);
	if (values.ocr_status) filters.push([doctype, "ocr_status", "=", values.ocr_status]);
	if (values.entry_status) filters.push([doctype, "entry_status", "=", values.entry_status]);
	if (party_field && values.party) filters.push([doctype, party_field, "=", values.party]);

	listview._tu_contenu = values.contenu || null;

	return Promise.resolve()
		.then(() => {
			// stale panel filters first (add() dedupes, so changed values must
			// have their old filter removed)
			const removals = fields_in_use.map((f) => listview.filter_area.remove(f));
			return Promise.all(removals);
		})
		.then(() => {
			if (!filters.length && !listview._tu_contenu) {
				listview.refresh();
				return;
			}
			return listview.filter_area.add(filters, !listview._tu_contenu);
		})
		.then(() => {
			// the OR set rides in get_args; a refresh applies it
			if (listview._tu_contenu) {
				listview.refresh();
			}
		});
};

erpnext.facturation.reset_filter_panel = function (listview) {
	listview._tu_contenu = null;
	const party_field = erpnext.facturation.party_field(listview.doctype);
	const removals = erpnext.facturation.filter_fieldnames
		.concat(party_field ? [party_field] : [])
		.map((f) => listview.filter_area.remove(f));
	Promise.all(removals).then(() => listview.refresh());
};

erpnext.facturation.prefill_filter_panel = function (listview, dialog) {
	const current = {};
	(listview.filter_area.get() || []).forEach((f) => {
		if (f[0] !== listview.doctype) return;
		current[f[1]] = { condition: f[2], value: f[3] };
	});
	const values = {};
	if (listview._tu_contenu) values.contenu = listview._tu_contenu;
	const strip = (v) => (typeof v === "string" ? v.replace(/^%|%$/g, "") : v);
	["mvt", "status", "ocr_status", "entry_status"].forEach((f) => {
		if (current[f]) values[f] = current[f].value;
	});
	["attachment", "description"].forEach((f) => {
		if (current[f]) values[f] = strip(current[f].value);
	});
	if (current.owner) values.owner_filter = current.owner.value;
	const party_field = erpnext.facturation.party_field(listview.doctype);
	if (party_field && current[party_field]) values.party = current[party_field].value;

	const from = current.posting_date && current.posting_date.condition === ">=" ? current.posting_date.value : null;
	const to = current.posting_date && current.posting_date.condition === "<=" ? current.posting_date.value : null;
	if (from && to) {
		// best-effort period detection from the stored range
		const d_from = frappe.datetime.str_to_obj(from);
		const d_to = frappe.datetime.str_to_obj(to);
		values.annee = String(d_from.getFullYear());
		const same_month =
			d_from.getDate() === 1 && d_to.getMonth() === d_from.getMonth() && d_from.getFullYear() === d_to.getFullYear();
		const end_of_month = new Date(d_from.getFullYear(), d_from.getMonth() + 1, 0).getDate() === d_to.getDate();
		const is_year =
			d_from.getMonth() === 0 && d_from.getDate() === 1 && d_to.getMonth() === 11 && d_to.getDate() === 31;
		if (is_year) {
			values.periode = "Annuelle";
		} else if (same_month && end_of_month) {
			values.periode = "Mensuelle";
			values.month = GL_MONTHS[d_from.getMonth()];
		} else {
			values.periode = "Personnalisee";
			values.du = from;
			values.au = to;
		}
	} else {
		if (from) values.du = from;
		if (to) values.au = to;
		if (from || to) values.periode = "Personnalisee";
	}
	if (values.periode) dialog.set_value("periode", values.periode);
	Object.keys(values).forEach((fieldname) => {
		if (dialog.fields_dict[fieldname]) dialog.set_value(fieldname, values[fieldname]);
	});
};
})();
