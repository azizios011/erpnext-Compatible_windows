frappe.pages["document-types"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Document Types"),
		single_column: true,
	});

	page.set_primary_action(
		__("Add"),
		function () {
			open_dialog();
		},
		"add"
	);

	var $container = $('<div class="document-types-container page-content"></div>').appendTo(page.main);

	function refresh_table() {
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Document Type Template",
				fields: ["name", "template_title", "voucher_type", "company", "is_opening"],
				order_by: "creation desc",
				limit_page_length: 0,
			},
			callback: function (r) {
				render_table(r.message || []);
			},
		});
	}

	function render_table(data) {
		$container.empty();

		if (!data || !data.length) {
			$container.html(
				'<div class="text-muted text-center p-5">' +
					__('No Document Type Templates found. Click "Add" to create one.') +
					"</div>"
			);
			return;
		}

		var $table = $(
			'<table class="table table-bordered table-hover align-middle">' +
				"<thead>" +
				"<tr>" +
				"<th>" + __("Template Title") + "</th>" +
				"<th>" + __("Journal Entry Type") + "</th>" +
				"<th>" + __("Company") + "</th>" +
				"<th>" + __("Is Opening") + "</th>" +
				'<th class="text-center" style="width: 140px;">' + __("Actions") + "</th>" +
				"</tr>" +
				"</thead>" +
				"<tbody></tbody>" +
				"</table>"
		);

		var $tbody = $table.find("tbody");

		data.forEach(function (row) {
			var $tr = $(
				"<tr>" +
					"<td><strong>" + frappe.utils.escape_html(row.template_title || row.name) + "</strong></td>" +
					"<td>" + frappe.utils.escape_html(row.voucher_type || "") + "</td>" +
					"<td>" + frappe.utils.escape_html(row.company || "") + "</td>" +
					"<td>" + frappe.utils.escape_html(row.is_opening || "No") + "</td>" +
					'<td class="text-center">' +
					'<div class="btn-group" role="group">' +
					'<button type="button" class="btn btn-default btn-xs edit-btn" title="' + __("Edit") + '"><i class="fa fa-pencil"></i></button> ' +
					'<button type="button" class="btn btn-default btn-xs open-form-btn" title="' + __("Open full form") + '"><i class="fa fa-external-link"></i></button> ' +
					'<button type="button" class="btn btn-default btn-xs text-danger delete-btn" title="' + __("Delete") + '"><i class="fa fa-trash"></i></button>' +
					"</div>" +
					"</td>" +
					"</tr>"
			);

			$tr.find(".edit-btn").on("click", function () {
				frappe.call({
					method: "frappe.client.get",
					args: {
						doctype: "Document Type Template",
						name: row.name,
					},
					callback: function (r) {
						if (r.message) {
							open_dialog(r.message);
						}
					},
				});
			});

			$tr.find(".open-form-btn").on("click", function () {
				frappe.set_route("Form", "Document Type Template", row.name);
			});

			$tr.find(".delete-btn").on("click", function () {
				frappe.confirm(
					__("Are you sure you want to delete {0}?", [row.template_title || row.name]),
					function () {
						frappe.call({
							method: "frappe.client.delete",
							args: {
								doctype: "Document Type Template",
								name: row.name,
							},
							callback: function (r) {
								if (!r.exc) {
									frappe.show_alert({ message: __("Deleted successfully"), indicator: "green" });
									refresh_table();
								}
							},
						});
					}
				);
			});

			$tbody.append($tr);
		});

		$container.append($table);
	}

	function open_dialog(doc) {
		var dialog = new frappe.ui.Dialog({
			title: doc ? __("Edit Document Type Template") : __("New Document Type Template"),
			fields: [
				{
					fieldname: "template_title",
					fieldtype: "Data",
					label: __("Template Title"),
					reqd: 1,
				},
				{
					fieldname: "voucher_type",
					fieldtype: "Select",
					label: __("Journal Entry Type"),
					options: [
						"Journal Entry",
						"Inter Company Journal Entry",
						"Bank Entry",
						"Cash Entry",
						"Credit Card Entry",
						"Debit Note",
						"Credit Note",
						"Contra Entry",
						"Excise Entry",
						"Write Off Entry",
						"Opening Entry",
						"Depreciation Entry",
						"Exchange Rate Revaluation",
					].join("\n"),
					reqd: 1,
				},
				{
					fieldname: "naming_series",
					fieldtype: "Select",
					label: __("Series"),
					reqd: 1,
				},
				{
					fieldname: "company",
					fieldtype: "Link",
					options: "Company",
					label: __("Company"),
					reqd: 1,
				},
				{
					fieldname: "is_opening",
					fieldtype: "Select",
					label: __("Is Opening"),
					options: "No\nYes",
					default: "No",
				},
				{
					fieldname: "multi_currency",
					fieldtype: "Check",
					label: __("Multi Currency"),
					default: 0,
				},
			],
			primary_action_label: doc ? __("Save") : __("Create"),
			primary_action: function (values) {
				if (doc) {
					var updated_doc = Object.assign({}, doc, values);
					frappe.call({
						method: "frappe.client.save",
						args: {
							doc: updated_doc,
						},
						callback: function (r) {
							if (!r.exc) {
								frappe.show_alert({ message: __("Updated successfully"), indicator: "green" });
								dialog.hide();
								refresh_table();
							}
						},
					});
				} else {
					values.doctype = "Document Type Template";
					frappe.call({
						method: "frappe.client.insert",
						args: {
							doc: values,
						},
						callback: function (r) {
							if (!r.exc) {
								frappe.show_alert({ message: __("Created successfully"), indicator: "green" });
								dialog.hide();
								refresh_table();
							}
						},
					});
				}
			},
		});

		frappe.call({
			method: "erpnext.custom_modules.general_accounting.doctype.document_type_template.document_type_template.get_naming_series",
			callback: function (r) {
				if (r.message) {
					var options = typeof r.message === "string" ? r.message.split("\n") : r.message;
					dialog.set_df_property("naming_series", "options", options);
					if (doc && doc.naming_series) {
						dialog.set_value("naming_series", doc.naming_series);
					} else if (options && options.length) {
						dialog.set_value("naming_series", options[0]);
					}
				}
			},
		});

		if (doc) {
			dialog.set_values({
				template_title: doc.template_title,
				voucher_type: doc.voucher_type,
				company: doc.company,
				is_opening: doc.is_opening || "No",
				multi_currency: doc.multi_currency || 0,
			});
		}

		dialog.show();
	}

	refresh_table();
};
