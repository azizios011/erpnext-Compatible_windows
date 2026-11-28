// Mensuelle: the declared figures (Déclaré tab) and the check results
// (Contrôles tab, rows coloured by severity). The figures themselves are
// written by the workbook import (facturation/api.py); Vérifier re-runs the
// checks, Ouvrir la déclaration routes to the month's Declaration Transaction.
frappe.ui.form.on("Mensuelle", {
	refresh(frm) {
		frm.add_custom_button(__("Vérifier"), () => verify_mensuelle(frm));
		if (!frm.is_new()) {
			frm.add_custom_button(__("Ouvrir la déclaration (Entries)"), () => {
				erpnext.facturation.open_entry("Mensuelle", frm.doc.name);
			});
		}
		color_controle_rows(frm);
	},
});

function verify_mensuelle(frm) {
	if (frm.is_new()) {
		frappe.msgprint({ message: __("Enregistrez la Mensuelle avant de la vérifier."), indicator: "orange" });
		return;
	}
	if (!frm.doc.source_file) {
		frappe.msgprint({
			message: __("Aucune feuille source: importez un classeur de déclaration mensuelle."),
			indicator: "orange",
		});
		return;
	}
	frappe.call({
		method: "erpnext.custom_modules.facturation.api.verify_mensuelle",
		args: { name: frm.doc.name },
		freeze: true,
		callback(r) {
			const result = r.message || {};
			frappe.show_alert({
				message: __("Contrôles: {0}", [result.status || ""]),
				indicator: result.status === "Conforme" ? "green" : result.status === "Ecarts" ? "red" : "orange",
			});
			frm.reload_doc();
		},
	});
}

// the Contrôles grid rows take a tint per severity (Erreur red,
// Avertissement orange, Info blue)
const MENSUELLE_SEVERITY_STYLES = `
	.mensuelle-severity-Erreur { background-color: rgba(206, 44, 44, 0.07) !important; }
	.mensuelle-severity-Avertissement { background-color: rgba(226, 153, 10, 0.08) !important; }
	.mensuelle-severity-Info { background-color: rgba(82, 146, 247, 0.07) !important; }
`;
let mensuelle_styles_injected = false;

function color_controle_rows(frm) {
	try {
		const field = frm.fields_dict.controles;
		if (!field || !field.grid) return;
		if (!mensuelle_styles_injected) {
			$("<style>").text(MENSUELLE_SEVERITY_STYLES).appendTo("head");
			mensuelle_styles_injected = true;
		}
		(field.grid.wrapper || $()).find(".grid-row").removeClass(
			"mensuelle-severity-Erreur mensuelle-severity-Avertissement mensuelle-severity-Info"
		);
		(frm.doc.controles || []).forEach((row) => {
			if (!row.severity || !row.name) return;
			const $row = field.grid.wrapper.find(`.grid-row[data-name="${row.name}"]`);
			$row.addClass(`mensuelle-severity-${row.severity}`);
		});
	} catch (error) {
		// colouring is cosmetic: never break the form
	}
}
