frappe.ui.form.on("RS Vente", {
	taxable_base(frm) {
		calculate_amounts(frm);
	},
	withholding_rate(frm) {
		calculate_amounts(frm);
	},
	tva_retenue_source(frm) {
		calculate_amounts(frm);
	}
});

function calculate_amounts(frm) {
	const base = flt(frm.doc.taxable_base);
	const rate = flt(frm.doc.withholding_rate);
	const tva_retenue = flt(frm.doc.tva_retenue_source);

	const amount_withheld = base * rate / 100;
	frm.set_value("amount_withheld", amount_withheld);
	frm.set_value("montant_servi", base - amount_withheld - tva_retenue);
}
