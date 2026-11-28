// Famille Declaration: the standard-model loader lives on both config forms
// (idempotent — existing records are never overwritten).
frappe.ui.form.on("Famille Declaration", {
	refresh(frm) {
		add_seed_declaration_config_button(frm);
	},
});

function add_seed_declaration_config_button(frm) {
	frm.add_custom_button(__("Charger le modèle standard"), () => {
		frappe.call({
			method: "erpnext.custom_modules.organization.declaration_config.seed_declaration_config",
			args: {},
			freeze: true,
			callback(r) {
				const result = r.message || {};
				const missing = result.missing_accounts || [];
				const lines = [
					__("Familles creees: {0} (deja presentes: {1})", [
						(result.familles_created || []).length,
						result.familles_existing ?? 0,
					]),
					__("Rubriques creees: {0} (deja presentes: {1})", [
						(result.rubriques_created || []).length,
						result.rubriques_existing ?? 0,
					]),
				];
				if (missing.length) {
					lines.push(__("Comptes absents du plan comptable (intervalle ignore): {0}", [missing.join(", ")]));
				}
				frappe.msgprint({
					title: __("Modele standard"),
					message: lines.join("<br>"),
					indicator: missing.length ? "orange" : "green",
				});
				frm.reload_doc();
			},
		});
	});
}
