// Entries-workspace entry point for the Facturation upload documents.
//
// The Facturation workspace only stores documents; the accounting entry for
// each one is produced later in the Entries workspace (stage 2). This file
// exposes erpnext.facturation.open_entry(doctype, name), which resolves the
// target entry doctype and either opens the already-linked entry or an
// UNSAVED new entry prefilled from the source document — nothing is
// auto-saved, the human reviews and saves. Registered globally through
// app_include_js; the per-row pen button of every Facturation list view and
// the "Saisie ecriture" form button both call it.
(function () {
	window.erpnext = window.erpnext || {};
	erpnext.facturation = erpnext.facturation || {};

	erpnext.facturation.open_entry = function (doctype, name) {
		frappe.call({
			method: "erpnext.custom_modules.facturation.facturation_base.get_entry_target",
			args: {
				doctype: doctype,
				name: name,
			},
			freeze: true,
			callback: function (r) {
				const target = r.message;
				if (!target || !target.entry_doctype) {
					return;
				}
				if (target.existing_entry) {
					frappe.set_route("Form", target.entry_doctype, target.existing_entry);
					return;
				}
				// route options prefill matching fields on the new form and are
				// consumed there; the document stays unsaved until reviewed
				frappe.new_doc(target.entry_doctype, target.defaults || {});
			},
		});
	};

	const FACTURATION_DOCTYPES = [
		"Facture Achat",
		"Releve Achat",
		"RS Achat",
		"Facture Vente",
		"RS Vente",
		"Releve Vente",
		"Releve Bancaire",
		"Remise de Cheque",
		"Virement Espece",
		"Mensuelle",
	];

	FACTURATION_DOCTYPES.forEach(function (doctype) {
		frappe.ui.form.on(doctype, {
			refresh(frm) {
				frm.add_custom_button(__("Saisie ecriture"), function () {
					erpnext.facturation.open_entry(frm.doctype, frm.doc.name);
				});
			},
		});
	});
})();
