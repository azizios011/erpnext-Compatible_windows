// The Lettrage tool is a classic Page (frappe.pages["lettrage"]) rendered by
// erpnext.lettrage — the single doctype form is never shown.
frappe.ui.form.on("Lettrage", {
	refresh() {
		frappe.set_route("lettrage");
	},
});
