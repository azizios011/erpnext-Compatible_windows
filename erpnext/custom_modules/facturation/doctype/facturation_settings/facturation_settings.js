frappe.ui.form.on("Facturation Settings", {
	refresh(frm) {
		if (frm.doc.model) {
			const current_options = frm.get_field("model").df.options || "";
			if (!current_options.split("\n").includes(frm.doc.model)) {
				frm.set_df_property("model", "options", frm.doc.model);
				frm.refresh_field("model");
			}
		}
	},
	provider(frm) {
		frm.set_df_property("model", "options", "");
		frm.set_value("model", "");
		frm.refresh_field("model");
	},
	refresh_models(frm) {
		if (!frm.doc.api_key) {
			frappe.msgprint(__("Please enter an API key first."));
			return;
		}
		if (!frm.doc.provider) {
			frappe.msgprint(__("Please select a provider first."));
			return;
		}

		frappe.dom.freeze(__("Fetching available models..."));

		frappe.call({
			method:
				"erpnext.custom_modules.facturation.doctype.facturation_settings.facturation_settings.get_available_models",
			args: {
				provider: frm.doc.provider,
				api_key: frm.doc.api_key,
			},
			callback: function (r) {
				frappe.dom.unfreeze();

				if (!r.message || !r.message.length) {
					frappe.msgprint(__("No models returned by the provider."));
					return;
				}

				const options = r.message.join("\n");
				frm.set_df_property("model", "options", options);
				frm.refresh_field("model");

				if (!frm.doc.model || !r.message.includes(frm.doc.model)) {
					frm.set_value("model", r.message[0]);
				}

				frappe.show_alert({
					message: __("Model list refreshed."),
					indicator: "green",
				});
			},
			error: function () {
				frappe.dom.unfreeze();
				frappe.msgprint(__("Failed to fetch models from the provider."));
			},
		});
	},
});
