frappe.pages["cash-flow-statement"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Cash flow statement"),
		single_column: true,
	});
};
