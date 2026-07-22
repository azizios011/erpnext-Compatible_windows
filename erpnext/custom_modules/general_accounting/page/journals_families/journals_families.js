frappe.pages["journals-families"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Journals (families)"),
		single_column: true,
	});
};
