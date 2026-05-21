// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Journals Creations", {
	onload: function (frm) {
		if (frm.is_new()) {
			frappe.call({
				type: "GET",
				method: "erpnext.tunisian_accounting.doctype.journals_creations.journals_creations.get_naming_series",
				callback: function (r) {
					if (r.message) {
						frm.set_df_property("naming_series", "options", r.message.split("\n"));
						frm.set_value("naming_series", r.message.split("\n")[0]);
						frm.refresh_field("naming_series");
					}
				},
			});
		}
	},
	refresh: function (frm) {
		frappe.model.set_default_values(frm.doc);
	}
});
