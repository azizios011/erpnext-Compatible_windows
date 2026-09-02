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
		if (frm.doc.attachment) {
			extract_invoice_data(frm);
		}
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
		? `<iframe src="${file_url}#toolbar=0&navpanes=0&scrollbar=0" style="width:100%; height:600px; border:1px solid var(--border-color); border-radius:4px;"></iframe>`
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

function extract_invoice_data(frm) {
	frappe.dom.freeze(__("Reading invoice data from the attached file..."));

	frappe.call({
		method:
			"erpnext.custom_modules.facturation.doctype.facture_vente.facture_vente.extract_invoice_data",
		args: {
			attachment: frm.doc.attachment,
		},
		callback: function (r) {
			frappe.dom.unfreeze();

			if (!r.message || !r.message.success) {
				const error_message = (r.message && r.message.error) || __("Unknown error.");
				frappe.msgprint({
					title: __("Extraction Failed"),
					message: error_message,
					indicator: "red",
				});
				return;
			}

			apply_extracted_data(frm, r.message.data);
		},
		error: function () {
			frappe.dom.unfreeze();
			frappe.msgprint({
				title: __("Extraction Failed"),
				message: __("Something went wrong while contacting the extraction service."),
				indicator: "red",
			});
		},
	});
}

function apply_extracted_data(frm, data) {
	if (!data) {
		return;
	}

	if (data.customer_name) {
		frm.set_value("customer_name", data.customer_name);
	}
	if (data.tax_id) {
		frm.set_value("tax_id", data.tax_id);
	}
	if (data.posting_date) {
		frm.set_value("posting_date", data.posting_date);
	}
	if (data.reference_number) {
		frm.set_value("reference_number", data.reference_number);
	}

	frm.clear_table("items");
	(data.items || []).forEach((item) => {
		const row = frm.add_child("items");
		row.description = item.description || "";
		row.qty = flt(item.qty) || 1;
		row.uom = item.uom || "";
		row.rate = flt(item.rate) || 0;
		row.amount = flt(row.qty) * flt(row.rate);
	});
	frm.refresh_field("items");

	frm.clear_table("taxes");
	(data.taxes || []).forEach((tax) => {
		const row = frm.add_child("taxes");
		row.charge_type = tax.charge_type || "Autre";
		row.rate = flt(tax.rate) || 0;
		row.base_amount = flt(tax.base_amount) || 0;
		row.tax_amount = flt(tax.tax_amount) || 0;
	});
	frm.refresh_field("taxes");

	calculate_totals(frm);

	frappe.show_alert({
		message: __("Invoice data extracted. Please review before saving."),
		indicator: "green",
	});
}
