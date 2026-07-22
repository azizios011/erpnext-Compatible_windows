frappe.pages["log-consultation"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Log consultation"),
		single_column: true,
	});
};
