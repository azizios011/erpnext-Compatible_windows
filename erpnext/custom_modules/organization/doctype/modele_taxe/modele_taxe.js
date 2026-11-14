// Modele Taxe: the line `compte` picker is a server-side link search over the
// non-group, non-disabled accounts of the context Entreprise (see
// organization/tiers_accounts.py — compte_search).
frappe.ui.form.on("Modele Taxe", {
	setup(frm) {
		frm.set_query("compte", "lignes", () => ({
			query: "erpnext.custom_modules.organization.tiers_accounts.compte_search",
		}));
	},
});
