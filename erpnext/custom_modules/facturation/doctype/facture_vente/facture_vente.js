// Facture Vente is an upload form (customer, posting date, reference,
// attachment, status): the attachment feeds the AI extraction, which fills
// the base fields only.
frappe.ui.form.on("Facture Vente", {
	refresh(frm) {
		bind_print_icon_override(frm);
	},
	attachment(frm) {
		if (frm.doc.attachment) {
			extract_invoice_data(frm);
		}
	},
});

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
				frm.set_value("ocr_status", "Echec");
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
			frm.set_value("ocr_status", "Echec");
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

	if (data.posting_date) {
		frm.set_value("posting_date", data.posting_date);
	}
	if (data.reference_number) {
		frm.set_value("reference_number", data.reference_number);
	}

	frm.set_value("ocr_status", "Termine");

	frappe.show_alert({
		message: __("Invoice data extracted. Please review before saving."),
		indicator: "green",
	});
}
