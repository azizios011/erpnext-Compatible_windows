// Chart of Account: a qualifying custom account under 411 can open a Client,
// one under 401 a Fournisseur — only when that account is not already bound.
frappe.ui.form.on("Chart of Account", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.is_group || frm.doc.is_standard || frm.doc.disabled) return;
		const number = frm.doc.account_number || "";
		const target =
			number.startsWith("411") && number.length > 3
				? "Client"
				: number.startsWith("401") && number.length > 3
					? "Fournisseur"
					: null;
		if (!target) return;
		frappe.db.exists(target, { account: frm.doc.name }).then((exists) => {
			if (exists) return;
			frm.add_custom_button(
				target === "Client" ? __("Créer un client") : __("Créer un fournisseur"),
				() => frappe.new_doc(target, { account: frm.doc.name })
			);
		});
	},
});
