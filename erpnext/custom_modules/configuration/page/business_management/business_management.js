frappe.pages["business-management"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Business Management"),
		single_column: true,
	});
};
