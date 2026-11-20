// Payable Print Format form: the buttons live in the shared Facturation layer
// (erpnext.facturation.print_format_form, facturation_entry.bundle.js), which
// calls the template engine with this doctype as template_doctype.
frappe.ui.form.on("Payable Print Format", {
	refresh(frm) {
		erpnext.facturation.print_format_form(frm);
	},
});
