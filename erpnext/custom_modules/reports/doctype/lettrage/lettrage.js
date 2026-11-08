// Lettrage tool form: the UI is rendered by erpnext.lettrage (the
// lettrage bundle, loaded via app_include_js) into the ui_html field.
frappe.ui.form.on("Lettrage", {
	refresh(frm) {
		if (window.erpnext && erpnext.lettrage) {
			erpnext.lettrage.render(frm);
		}
	},
});
