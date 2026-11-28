// Declaration Transaction: the Déclaration Mensuelle screen. The document is
// computed from the ledger by erpnext.custom_modules.entries.declaration_engine
// (the rubriques + totaux HTML are rendered server-side at compute time);
// the form only drives the workflow Brouillon -> Cloture -> Depose.
frappe.ui.form.on("Declaration Transaction", {
	refresh(frm) {
		show_dm_status(frm);
		show_dm_headline(frm);
		render_dm_buttons(frm);
		wire_rubrique_drill_down(frm);
	},
});

function show_dm_status(frm) {
	const status = frm.doc.status || "Brouillon";
	const theme = status === "Depose" ? "green" : status === "Cloture" ? "blue" : "orange";
	frm.page.set_indicator(__(status), theme);
}

function show_dm_headline(frm) {
	// the dock context header (never a company picker: the context decides)
	const parts = [];
	const context_headline =
		window.axeane && axeane.context && axeane.context.headline ? axeane.context.headline() : "";
	if (context_headline) {
		parts.push(frappe.utils.escape_html(context_headline));
	}
	if (frm.doc.mensuelle) {
		const label = frappe.utils.escape_html(__("Mensuelle") + " " + frm.doc.mensuelle);
		parts.push(
			__("Source: {0}", [frappe.utils.get_form_link("Mensuelle", frm.doc.mensuelle, true, label)])
		);
	}
	if (frm.doc.status === "Depose" && frm.doc.numero_declaration) {
		parts.push(
			__("Recu portail {0} — liquidé {1}", [
				frappe.utils.escape_html(frm.doc.numero_declaration),
				dm_money(frm.doc.montant_liquide),
			])
		);
	}
	frm.dashboard.set_headline(parts.join(" &nbsp;—&nbsp; "));
}

function render_dm_buttons(frm) {
	const status = frm.doc.status || "Brouillon";
	if (status === "Brouillon") {
		frm.add_custom_button(__("Calculer"), () => compute_dm(frm), __("Declaration"));
		frm.add_custom_button(__("Clôturer"), () => cloture_dm(frm), __("Declaration"));
		frm.page.set_primary_action(__("Enregistrer"), () => frm.save());
	} else if (status === "Cloture") {
		frm.add_custom_button(__("Dé-clôturer"), () => decloture_dm(frm), __("Declaration"));
		frm.add_custom_button(__("Déposer"), () => depose_dm(frm), __("Declaration"));
		frm.page.set_primary_action("", () => {});
	} else {
		// Depose: irreversible — nothing to do but read
		frm.page.set_primary_action("", () => {});
	}
}

function compute_dm(frm) {
	const is_new = frm.is_new();
	const mois = frm.doc.mois;
	const type_declaration = frm.doc.type_declaration || "Principale";
	if (!mois) {
		frappe.msgprint({ message: __("Choisissez le mois de la declaration."), indicator: "orange" });
		return;
	}
	frappe.call({
		method: "erpnext.custom_modules.entries.declaration_engine.compute_declaration",
		args: { mois, type_declaration, mensuelle: frm.doc.mensuelle || "" },
		freeze: true,
		callback(r) {
			const dm = r.message || {};
			frappe.show_alert({
				message: __("Declaration calculee: TVA a payer {0}, total {1}", [
					format_dm_money(dm.tva_a_payer),
					format_dm_money(dm.total_a_payer),
				]),
				indicator: "green",
			});
			if (is_new) {
				frappe.set_route("Form", "Declaration Transaction", dm.name);
			} else {
				frm.reload_doc();
			}
		},
	});
}

function cloture_dm(frm) {
	frappe.confirm(
		__("Cloturer la declaration {0}? Les ecritures utilisees seront verrouillees.", [frm.doc.name]),
		() => {
			frappe.call({
				method: "erpnext.custom_modules.entries.declaration_engine.cloture_declaration",
				args: { name: frm.doc.name },
				freeze: true,
				callback(r) {
					const result = r.message || {};
					frappe.show_alert({
						message: __("Declaration cloturee ({0} ecritures verrouillees).", [
							result.rows_stamped ?? 0,
						]),
						indicator: "blue",
					});
					frm.reload_doc();
				},
			});
		}
	);
}

function decloture_dm(frm) {
	frappe.call({
		method: "erpnext.custom_modules.entries.declaration_engine.decloture_declaration",
		args: { name: frm.doc.name },
		freeze: true,
		callback() {
			frappe.show_alert({ message: __("Declaration de-cloturee."), indicator: "orange" });
			frm.reload_doc();
		},
	});
}

function depose_dm(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Deposer la declaration — recu portail e-tasrih"),
		fields: [
			{ fieldname: "numero_declaration", fieldtype: "Data", label: __("N° declaration"), reqd: 1 },
			{
				fieldname: "situation_paiement",
				fieldtype: "Select",
				label: __("Situation paiement"),
				options: "Liquidee\nPayee\nAnnulee",
				default: "Liquidee",
				reqd: 1,
			},
			{ fieldname: "cb1", fieldtype: "Column Break" },
			{ fieldname: "acte", fieldtype: "Int", label: __("Acte (0 = principal)"), default: 0 },
			{ fieldname: "montant_liquide", fieldtype: "Currency", label: __("Montant liquide"), precision: 3 },
			{ fieldname: "cb2", fieldtype: "Column Break" },
			{ fieldname: "date_liquidation", fieldtype: "Date", label: __("Date liquidation") },
			{ fieldname: "date_operation", fieldtype: "Date", label: __("Date operation") },
			{ fieldname: "cb3", fieldtype: "Column Break" },
			{ fieldname: "mode_paiement", fieldtype: "Data", label: __("Mode paiement") },
			{ fieldname: "quittance", fieldtype: "Data", label: __("Quittance") },
			{ fieldname: "date_depot", fieldtype: "Datetime", label: __("Depose le"), default: frappe.datetime.now_datetime() },
		],
		primary_action_label: __("Deposer"),
		primary_action(values) {
			frappe.call({
				method: "erpnext.custom_modules.entries.declaration_engine.depose_declaration",
				args: {
					name: frm.doc.name,
					numero_declaration: values.numero_declaration,
					situation_paiement: values.situation_paiement,
					acte: values.acte || 0,
					date_liquidation: values.date_liquidation || "",
					date_operation: values.date_operation || "",
					mode_paiement: values.mode_paiement || "",
					quittance: values.quittance || "",
					montant_liquide: values.montant_liquide || 0,
					date_depot: values.date_depot,
				},
				freeze: true,
				callback() {
					dialog.hide();
					frappe.show_alert({ message: __("Declaration deposee."), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

function wire_rubrique_drill_down(frm) {
	const wrapper = frm.fields_dict.rubriques_html && frm.fields_dict.rubriques_html.$wrapper;
	if (!wrapper) return;
	wrapper.off("click.dm-drill-down").on("click.dm-drill-down", ".dm-rubrique-row", function () {
		const code = $(this).attr("data-code");
		if (!code || !frm.doc.name || frm.is_new()) return;
		frappe.call({
			method: "erpnext.custom_modules.entries.declaration_engine.get_rubrique_ledger",
			args: { name: frm.doc.name, code },
			callback(r) {
				show_rubrique_ledger_dialog(r.message || {});
			},
		});
	});
}

function show_rubrique_ledger_dialog(result) {
	const esc = frappe.utils.escape_html;
	const rows = result.rows || [];
	const body_rows = rows
		.map(
			(row) =>
				`<tr>
					<td>${frappe.datetime.str_to_user(row.posting_date)}</td>
					<td>${esc(row.journal || "")}</td>
					<td>${esc(row.mvt || "")}</td>
					<td>${esc(row.account || "")}</td>
					<td>${esc(row.libelle || "")}</td>
					<td style="text-align:right;">${format_dm_money(row.debit)}</td>
					<td style="text-align:right;">${format_dm_money(row.credit)}</td>
					<td>${
						row.source_entry_doctype && row.source_entry
							? frappe.utils.get_form_link(row.source_entry_doctype, row.source_entry, true, __("Ouvrir"))
							: ""
					}</td>
				</tr>`
		)
		.join("");
	const dialog = new frappe.ui.Dialog({
		title: __("Ecritures de la rubrique {0}", [result.code || ""]),
		size: "extra-large",
		fields: [
			{
				fieldname: "table_html",
				fieldtype: "HTML",
				options: `<div style="max-height:420px;overflow:auto;">
					<table class="table table-bordered" style="margin-bottom:0;">
						<thead><tr><th>Date</th><th>Jrn</th><th>Mvt</th><th>Compte</th><th>Libelle</th>
						<th style="text-align:right;">Debit</th><th style="text-align:right;">Credit</th><th></th></tr></thead>
						<tbody>${body_rows || '<tr><td colspan="8">' + __("Aucune ecriture.") + "</td></tr>"}</tbody>
						<tfoot><tr style="font-weight:600;"><td colspan="5">${__("Totaux")}</td>
						<td style="text-align:right;">${format_dm_money(result.total_debit)}</td>
						<td style="text-align:right;">${format_dm_money(result.total_credit)}</td><td></td></tr></tfoot>
					</table></div>`,
			},
		],
	});
	dialog.show();
}

function format_dm_money(value) {
	return (value || 0).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
}
