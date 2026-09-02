frappe.ui.form.on("Facture Vente", {
	refresh(frm) {
		calculate_totals(frm);
	},
	validate(frm) {
		calculate_totals(frm);
	}
});

frappe.ui.form.on("Facture Vente Item", {
	qty(frm, cdt, cdn) {
		update_item_amount(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		update_item_amount(frm, cdt, cdn);
	},
	items_remove(frm) {
		calculate_totals(frm);
	}
});

frappe.ui.form.on("Facture Vente Tax", {
	tax_amount(frm) {
		calculate_totals(frm);
	},
	taxes_remove(frm) {
		calculate_totals(frm);
	}
});

function update_item_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	row.amount = flt(row.qty) * flt(row.rate);
	frm.refresh_field("items");
	calculate_totals(frm);
}

function calculate_totals(frm) {
	let total_ht = 0;
	(frm.doc.items || []).forEach((row) => {
		total_ht += flt(row.amount);
	});

	let total_taxes = 0;
	(frm.doc.taxes || []).forEach((row) => {
		total_taxes += flt(row.tax_amount);
	});

	frm.set_value("total_ht", total_ht);
	frm.set_value("total_taxes_and_charges", total_taxes);
	frm.set_value("grand_total", total_ht + total_taxes);
	frm.refresh_fields();
}
