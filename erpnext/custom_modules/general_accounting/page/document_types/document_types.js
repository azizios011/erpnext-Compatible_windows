frappe.pages["document-types"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Document Types"),
		single_column: true,
	});
};
