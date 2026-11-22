// Banque: the account picker is the shared tiers link search restricted to
// custom accounts of class 5 of the context Entreprise (see
// organization/tiers_accounts.py); the journal picker is a server-side
// search over the free Banque journals; bank_name prefills from the
// account's libelle — still editable; "Creer un journal" opens a dialog
// suggesting the next free BQ code and "Banque - <bank_name>".
frappe.ui.form.on("Banque", {
	setup(frm) {
		frm.set_query("account", () => ({
			query: "erpnext.custom_modules.organization.tiers_accounts.tiers_account_search",
			filters: { current_name: frm.doc.name },
		}));
		frm.set_query("journal", () => ({
			query: "erpnext.custom_modules.organization.doctype.banque.banque.journal_search",
			filters: { current_name: frm.doc.name },
		}));
	},
	account(frm) {
		if (frm.doc.account && !frm.doc.bank_name) {
			frappe.db.get_value("Chart of Account", frm.doc.account, "account_name", (r) => {
				if (r && r.account_name) frm.set_value("bank_name", r.account_name);
			});
		}
	},
	refresh(frm) {
		frm.add_custom_button(__("Creer un journal"), () => open_journal_dialog(frm));
	},
});

function open_journal_dialog(frm) {
	frappe.call({
		method: "erpnext.custom_modules.organization.doctype.banque.banque.next_journal_code",
		callback(r) {
			const suggestion = (r.message && r.message.code) || "BQ1";
			const d = new frappe.ui.Dialog({
				title: __("Creer un journal"),
				fields: [
					{ fieldname: "code", fieldtype: "Data", label: __("Code"), reqd: 1, default: suggestion },
					{
						fieldname: "name",
						fieldtype: "Data",
						label: __("Nom"),
						reqd: 1,
						default: frm.doc.bank_name ? `Banque - ${frm.doc.bank_name}` : "",
					},
				],
				primary_action_label: __("Creer"),
				primary_action(values) {
					frappe.call({
						method: "erpnext.custom_modules.organization.doctype.banque.banque.create_journal",
						args: { code: values.code, name: values.name },
						freeze: true,
						callback(res) {
							d.hide();
							if (res.message && res.message.journal) {
								frm.set_value("journal", res.message.journal);
								frappe.show_alert({
									message: __("Journal {0} cree.", [res.message.journal]),
									indicator: "green",
								});
							}
						},
					});
				},
			});
			d.show();
		},
	});
}
