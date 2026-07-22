frappe.pages["chart-of-accounts"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Chart of Accounts"),
		single_column: true,
	});
};
