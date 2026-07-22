frappe.pages["account-query"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Account Query"),
		single_column: true,
	});
};
