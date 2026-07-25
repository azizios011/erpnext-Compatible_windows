// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Document Type Template", {
	onload: function (frm) {
		erpnext.accounts.dimensions.setup_dimension_filters(frm, frm.doctype);
	},
	refresh: function (frm) {
		frappe.model.set_default_values(frm.doc);

		frm.set_query("account", "accounts", function () {
			var filters = {
				company: frm.doc.company,
				is_group: 0,
			};

			return { filters: filters };
		});

		frm.set_query("project", "accounts", function (doc, cdt, cdn) {
			let row = frappe.get_doc(cdt, cdn);
			let filters = {
				company: doc.company,
			};
			if (row.party_type == "Customer") {
				filters.customer = row.party;
			}
			return {
				query: "erpnext.controllers.queries.get_project_name",
				filters,
			};
		});

		frm.set_query("party_type", "accounts", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];

			return {
				query: "erpnext.setup.doctype.party_type.party_type.get_party_type",
				filters: {
					account: row.account,
				},
			};
		});
	},
});
