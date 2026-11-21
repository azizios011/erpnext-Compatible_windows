// Receivable Print Format form: the shared Facturation layer (erpnext.facturation.print_format_form,
// facturation_entry.bundle.js) adds the Validate / Preview buttons and the
// sidebar prompt dropdown; the sidebar stays visible on new records via the
// frappe.form_sidebar.visible_on_new opt-in.
frappe.ui.form.on("Receivable Print Format", {
	refresh(frm) {
		if (erpnext.facturation && erpnext.facturation.print_format_form) {
			erpnext.facturation.print_format_form(frm);
		}
	},
});
