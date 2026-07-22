frappe.pages["scanned-document-capture"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Scanned document capture"),
		single_column: true,
	});
};
