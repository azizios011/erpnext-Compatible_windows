// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Journals Creations", {
	onload(frm) {
		if (frm.is_new()) {
			frappe.call({
				type: "GET",
				method: "erpnext.tunisian_accounting.doctype.journals_creations.journals_creations.get_naming_series",
				callback(r) {
					if (r.message) {
						frm.set_df_property("naming_series", "options", r.message.split("\n"));
						frm.set_value("naming_series", r.message.split("\n")[0]);
						frm.refresh_field("naming_series");
					}
				},
			});
		}
	},

	setup(frm) {
		frm.set_query("account", "accounting_entries", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
			},
		}));

		frm.set_query("tresorerie", "accounting_entries", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				account_type: ["in", ["Bank", "Cash"]],
			},
		}));
	},

	refresh(frm) {
		frappe.model.set_default_values(frm.doc);
		update_line_numbers(frm);
	},

	company(frm) {
		(frm.doc.accounting_entries || []).forEach((row) => {
			row.account = "";
			row.tresorerie = "";
		});
		frm.refresh_field("accounting_entries");
	},
});

frappe.ui.form.on("Journals Creations Detail", {
	accounting_entries_add(frm) {
		update_line_numbers(frm);
	},

	accounting_entries_remove(frm) {
		update_line_numbers(frm);
	},
});

function update_line_numbers(frm) {
	(frm.doc.accounting_entries || []).forEach((row, index) => {
		row.line_no = index + 1;
	});
	frm.refresh_field("accounting_entries");
}
