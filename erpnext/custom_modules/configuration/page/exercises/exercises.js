frappe.pages["exercises"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Exercises"),
		single_column: true,
	});
};
