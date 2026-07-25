// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Document Type Template", {
	onload: function (frm) {
		erpnext.accounts.dimensions.setup_dimension_filters(frm, frm.doctype);
	},
	refresh: function (frm) {
		frappe.model.set_default_values(frm.doc);
		setup_amount_breakdown(frm);
	},
	entry_mode: function (frm) {
		setup_amount_breakdown(frm);
	},
});

function setup_amount_breakdown(frm) {
	if (frm.doc.entry_mode === "Single") {
		frm.set_df_property("amount_breakdown", "cannot_add_rows", true);
		frm.set_df_property("amount_breakdown", "cannot_delete_rows", true);

		if (!frm.doc.amount_breakdown || frm.doc.amount_breakdown.length === 0) {
			["TTC", "TVA", "HT TVA", "Timbre"].forEach((comp) => {
				let row = frappe.model.add_child(frm.doc, "Document Type Template Amount", "amount_breakdown");
				row.component = comp;
			});
		}
		frm.refresh_field("amount_breakdown");
	} else {
		frm.set_df_property("amount_breakdown", "cannot_add_rows", false);
		frm.set_df_property("amount_breakdown", "cannot_delete_rows", false);
		frm.refresh_field("amount_breakdown");
	}
}
