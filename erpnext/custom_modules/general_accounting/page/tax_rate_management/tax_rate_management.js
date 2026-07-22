frappe.pages["tax-rate-management"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tax rate management"),
		single_column: true,
	});
};
