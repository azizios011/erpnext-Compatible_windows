frappe.pages["cash-flow"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Cash Flow"),
		single_column: true,
	});
};
