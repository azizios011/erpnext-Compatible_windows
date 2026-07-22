frappe.pages["treatments"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Treatments"),
		single_column: true,
	});
};
