frappe.require("/assets/erpnext/js/facturation/entries_grid.js").then(() => {
	frappe.ui.form.on("Releve Vente", {
		refresh(frm) {
			new erpnext.facturation.EntriesGrid({
				frm: frm,
				field: "entries_html",
				child_doctype: "Releve Vente Detail",
				parent_field: "releve_vente",
				page_length: 20,
				columns: [
					{ fieldname: "client_code", label: __("Client Code"), width: 100 },
					{ fieldname: "client_name", label: __("Client Name"), width: 160 },
					{ fieldname: "operation", label: __("Operation"), width: 90 },
					{ fieldname: "reference", label: __("Reference"), width: 130 },
					{ fieldname: "date", label: __("Date"), width: 100 },
					{ fieldname: "ttc", label: __("TTC"), width: 100, align: "right" },
					{ fieldname: "ht", label: __("HT"), width: 100, align: "right" },
					{ fieldname: "remise", label: __("Remise"), width: 90, align: "right" },
					{ fieldname: "tot_net_ht", label: __("Tot. Net. HT"), width: 100, align: "right" },
					{ fieldname: "tva_percent", label: __("TVA %"), width: 80, align: "right" },
					{ fieldname: "montant_tva", label: __("Montant TVA"), width: 100, align: "right" },
				],
			});
		},
	});
});
