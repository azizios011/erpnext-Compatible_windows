// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Chart of Accounts", {
	refresh: function (frm) {
		frappe.model.set_default_values(frm.doc);
	},
});
