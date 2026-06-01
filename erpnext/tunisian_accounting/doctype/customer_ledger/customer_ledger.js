// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Customer Ledger", {
	refresh(frm) {
		frm.add_custom_button(__("Load Entries"), () => load_ledger_entries(frm));
		if (!frm.is_new()) {
			load_ledger_entries(frm, true);
		}
	},
});

function load_ledger_entries(frm, silent = false) {
	if (!frm.doc.company || !frm.doc.from_date || !frm.doc.to_date) {
		if (!silent) {
			frappe.msgprint(__("Please set Company, From Date, and To Date."));
		}
		return;
	}

	frappe.call({
		method: "erpnext.tunisian_accounting.doctype.customer_ledger.customer_ledger.get_entries",
		args: {
			company: frm.doc.company,
			from_date: frm.doc.from_date,
			to_date: frm.doc.to_date,
			customer: frm.doc.customer,
		},
		freeze: true,
		callback(r) {
			frm.clear_table("entries");
			(r.message || []).forEach((row) => {
				const entry = frm.add_child("entries");
				Object.assign(entry, row);
			});
			frm.refresh_field("entries");
			if (!r.message?.length && !silent) {
				frappe.msgprint(
					__(
						"No submitted customer invoices (Entry of Entries) found for this period."
					)
				);
			}
		},
	});
}
