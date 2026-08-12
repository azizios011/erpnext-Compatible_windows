frappe.pages["notifications"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Notifications"),
		single_column: true,
	});
};
