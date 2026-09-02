frappe.ui.form.on("Facture Vente", {
	refresh(frm) {
		calculate_totals(frm);
		render_attachment_preview(frm);
		bind_print_icon_override(frm);
	},
	validate(frm) {
		calculate_totals(frm);
	},
	attachment(frm) {
		render_attachment_preview(frm);
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

function render_attachment_preview(frm) {
	if (!frm.fields_dict.attachment_preview) {
		return;
	}

	if (!frm.doc.attachment) {
		frm.set_df_property("attachment_preview", "options", "");
		frm.refresh_field("attachment_preview");
		return;
	}

	const file_url = frm.doc.attachment;
	const is_pdf = file_url.toLowerCase().endsWith(".pdf");
	const html = is_pdf
		? `<iframe src="${file_url}" style="width:100%; height:600px; border:1px solid var(--border-color); border-radius:4px;"></iframe>`
		: `<img src="${file_url}" style="max-width:100%; max-height:600px; display:block; border-radius:4px;">`;

	frm.set_df_property("attachment_preview", "options", html);
	frm.refresh_field("attachment_preview");
}

function bind_print_icon_override(frm) {
	if (frm.is_new()) {
		return;
	}

	setTimeout(() => {
		const $sidebar = frm.page.wrapper.find(".form-sidebar, .layout-side-section");
		if (!$sidebar.length) {
			return;
		}

		$sidebar
			.find("[title='Print'], [data-original-title='Print'], .icon-print, [aria-label='Print']")
			.off("click.facture_vente_print")
			.on("click.facture_vente_print", function (e) {
				e.preventDefault();
				e.stopPropagation();
				frm.print_doc();
			});
	}, 300);
}
