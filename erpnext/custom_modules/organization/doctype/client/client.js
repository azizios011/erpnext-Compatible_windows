// Client: the account picker is a server-side link search restricted to
// custom accounts under 411 of the context Entreprise (see
// organization/tiers_accounts.py), and the name prefills from the account's
// libelle — still editable.
frappe.ui.form.on("Client", {
	setup(frm) {
		frm.set_query("account", () => ({
			query: "erpnext.custom_modules.organization.tiers_accounts.tiers_account_search",
			filters: { current_name: frm.doc.name },
		}));
	},
	account(frm) {
		if (frm.doc.account && !frm.doc.client_name) {
			frappe.db.get_value("Chart of Account", frm.doc.account, "account_name", (r) => {
				if (r && r.account_name) frm.set_value("client_name", r.account_name);
			});
		}
	},
});
