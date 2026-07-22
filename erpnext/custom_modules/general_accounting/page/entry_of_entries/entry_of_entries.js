frappe.pages["entry-of-entries"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Entry of entries"),
		single_column: true,
	});
};
