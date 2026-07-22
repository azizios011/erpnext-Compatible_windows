frappe.pages["general-ledger"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("General Ledger"),
		single_column: true,
	});
};
