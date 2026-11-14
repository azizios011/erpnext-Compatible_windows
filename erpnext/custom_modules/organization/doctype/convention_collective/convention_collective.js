// Nombre d'heures is computed from Nombre de jours (8h/day, see the
// controller's HEURES_PAR_JOUR) — recomputed live, never typed.
frappe.ui.form.on("Convention Collective", {
	refresh(frm) {
		frm.add_custom_button(__("Importer depuis Excel"), () => lookup_import_dialog("Convention Collective"));
	},
	nombre_jours(frm) {
		frm.set_value("nombre_heures", flt(frm.doc.nombre_jours) * 8);
	},
});

// Shared by the lookup doctypes (Activite, Convention Collective,
// Forme Juridique): pick an .xlsx, send it base64 to
// organization.lookup_import.import_lookup_xlsx, report the counts.
// Note: the controller recomputes nombre_heures from nombre_jours on validate,
// so an "heures" column in the file is ignored on purpose.
function lookup_import_dialog(doctype) {
	const dialog = new frappe.ui.Dialog({
		title: __("Importer depuis Excel"),
		fields: [
			{
				fieldname: "fichier",
				fieldtype: "HTML",
				options:
					'<input type="file" accept=".xlsx" class="form-control" ' +
					'style="padding: 4px;" aria-label="' +
					__("Fichier Excel") +
					'">',
			},
		],
		primary_action_label: __("Importer"),
		primary_action() {
			const input = dialog.$wrapper.find('input[type="file"]')[0];
			const file = input?.files?.[0];
			if (!file || !file.name.toLowerCase().endsWith(".xlsx")) {
				frappe.msgprint({ message: __("Choisissez un fichier Excel .xlsx."), indicator: "red" });
				return;
			}
			const reader = new FileReader();
			reader.onload = () => {
				const base64 = String(reader.result).split(",")[1] || "";
				frappe.call({
					method: "erpnext.custom_modules.organization.lookup_import.import_lookup_xlsx",
					args: { doctype, content_base64: base64, dry_run: 0 },
					freeze: true,
					freeze_message: __("Import en cours..."),
					callback(r) {
						const s = r.message || {};
						frappe.show_alert({
							message: __("Import terminé: {0} créé(s), {1} déjà existant(s), {2} erreur(s).", [
								s.created ?? 0,
								s.deja_existants ?? 0,
								s.error_count ?? 0,
							]),
							indicator: s.ok ? "green" : "orange",
						});
						if (s.error_count > 0) {
							frappe.msgprint({
								title: __("Erreurs d'import"),
								message: (s.errors || [])
									.map((e) => `${__(e.sheet)} · ${e.row ?? "—"} : ${e.message}`)
									.join("<br>"),
								indicator: "red",
							});
						}
						dialog.hide();
					},
				});
			};
			reader.readAsDataURL(file);
		},
	});
	dialog.show();
}
