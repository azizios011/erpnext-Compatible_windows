frappe.pages["sending-documents"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Sending Documents"),
		single_column: true,
	});
};
