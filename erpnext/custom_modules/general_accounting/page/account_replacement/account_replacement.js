frappe.pages["account-replacement"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Account Replacement"),
		single_column: true,
	});
};
