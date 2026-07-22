frappe.pages["lettering"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Lettering"),
		single_column: true,
	});
};
