// Receivable Transaction: "Modification ecritures" screen; shared behaviour lives in
// erpnext.entries (public/js/entry_form.js, loaded via app_include_js).
frappe.ui.form.on("Receivable Transaction", {
	refresh(frm) {
		erpnext.entries.entry_form(frm);
		erpnext.entries.load_entry_defaults(frm);
	},
	date_operation(frm) {
		erpnext.entries.derive_period(frm);
	},
	apply_libelle_to_lines(frm) {
		erpnext.entries.apply_libelle(frm);
	},
	libelle(frm) {
		erpnext.entries.apply_libelle(frm);
	},
});
