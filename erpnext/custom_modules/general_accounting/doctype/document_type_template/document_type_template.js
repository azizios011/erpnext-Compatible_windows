// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Document Type Template", {
	onload: function (frm) {
		erpnext.accounts.dimensions.setup_dimension_filters(frm, frm.doctype);
	},
	refresh: function (frm) {
		frappe.model.set_default_values(frm.doc);
	},
});
