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

	erpnext.facturation.open_entry = function (doctype, name) {
		frappe.call({
			method: "erpnext.custom_modules.facturation.facturation_base.get_entry_target",
			args: {
				doctype: doctype,
				name: name,
			},
			freeze: true,
			callback: function (r) {
				const target = r.message;
				if (!target || !target.entry_doctype) {
					return;
				}
				if (target.existing_entry) {
					frappe.set_route("Form", target.entry_doctype, target.existing_entry);
					return;
				}
				// route options prefill matching fields on the new form and are
				// consumed there; the document stays unsaved until reviewed
				frappe.new_doc(target.entry_doctype, target.defaults || {});
			},
		});
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
			},
		});
	});
})();

// ── Facturation list views ───────────────────────────────────────────────────
// Top bar reduced to the Filter control, the Axeane "Validation Documents
// Comptables" filter panel, the pen button inside the row's activity
// cluster and two injected columns (Date transfert / Envoye par — creation
// and owner are not docfields, so the fixtures cannot carry them).

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

/** Called once per list view (settings.onload). */
erpnext.facturation.setup_list = function (listview) {
	// top bar: nothing but the Filtres Axeane button — no ID/standard
	// inputs, no frappe Filter popover, no sort selector (the doctype JSON
	// keeps posting_date DESC)
	safe(function () {
		listview.page.page_form.find(".standard-filter-section").addClass("hidden");
		if (listview.$filter_section) {
			listview.$filter_section.addClass("hidden");
		}
		if (listview.sort_selector && listview.sort_selector.wrapper) {
			listview.sort_selector.wrapper.addClass("hidden");
		}
	});
	safe(function () {
		erpnext.facturation.setup_contenu_args(listview);
	});
	safe(function () {
		erpnext.facturation.setup_row_delegation(listview);
	});
	safe(function () {
		listview.page.add_inner_button(__("Filtres Axeane"), function () {
			safe(function () {
				erpnext.facturation.filter_panel(listview);
			});
		});
	});
};

/** Called after every render (settings.refresh). setup_list is idempotent
 * and runs here too, so the top bar and button are in place even if the
 * onload hook never fired. Every step is guarded: our code can never blank
 * the rendered table. */
erpnext.facturation.on_list_refresh = function (listview) {
	safe(function () {
		erpnext.facturation.setup_list(listview);
	});
	safe(function () {
		erpnext.facturation.inject_row_buttons(listview);
	});
	safe(function () {
		erpnext.facturation.inject_extra_columns(listview);
	});
};

/** The pen button lives in the row's activity cluster (time · comments ·
 * like), not in its own column. Re-injected after every render; the
 * delegated click resolves the row name from the subject link. */
erpnext.facturation.inject_row_buttons = function (listview) {
	listview.$result.find(".list-row-container").each(function (i, el) {
		const $row = $(el);
		if ($row.find(".tu-entry-btn").length) {
			return;
		}
		const name = $row.find("a[data-name]").attr("data-name");
		if (!name) {
			return;
		}
		const $activity = $row.find(".list-row-activity").first();
		if (!$activity.length) {
			return;
		}
		$(
			'<button class="btn btn-xs btn-default tu-entry-btn" data-tu-name="' +
				frappe.utils.escape_html(name) +
				'" title="' +
				__("Saisie ecriture") +
				'">' +
				frappe.utils.icon("square-pen", "xs") +
				"</button>"
		).prependTo($activity);
	});
};

erpnext.facturation.setup_row_delegation = function (listview) {
	if (listview.__tu_row_delegation) {
		return;
	}
	listview.__tu_row_delegation = true;
	listview.$result.on("click", ".tu-entry-btn", function (e) {
		e.stopPropagation();
		e.preventDefault();
		const name = $(this).attr("data-tu-name");
		if (name) {
			erpnext.facturation.open_entry(listview.doctype, name);
		}
	});
};

/** Date transfert (creation) and Envoye par (owner) columns. */
erpnext.facturation.inject_extra_columns = function (listview) {
	const $head = listview.$result
		.find(".list-row-head .level-left.list-header-subject")
		.first();
	if (!$head.length) {
		return;
	}
	if (!$head.find(".tu-col-creation").length) {
		$head.append(
			'<div class="list-row-col hidden-xs tu-col tu-col-creation ellipsis">' +
				__("Date transfert") +
				"</div>"
		);
		$head.append(
			'<div class="list-row-col hidden-xs tu-col tu-col-owner ellipsis">' +
				__("Envoye par") +
				"</div>"
		);
	}
	listview.$result.find(".list-row-container").each(function (i, el) {
		const $row = $(el);
		if ($row.find(".tu-col-creation").length) {
			return;
		}
		const name = $row.find("a[data-name]").attr("data-name");
		const doc = (listview.data || []).find((d) => d.name === name) || {};
		const creation = doc.creation ? frappe.datetime.str_to_user(doc.creation) : "";
		const owner = doc.owner ? frappe.user_info(doc.owner).fullname || doc.owner : "";
		const $left = $row.find(".level-left").first();
		$(
			'<div class="list-row-col hidden-xs tu-col tu-col-creation ellipsis">' +
				frappe.utils.escape_html(creation) +
				"</div>"
		).appendTo($left);
		$(
			'<div class="list-row-col hidden-xs tu-col tu-col-owner ellipsis">' +
				frappe.utils.escape_html(owner) +
				"</div>"
		).appendTo($left);
	});
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
