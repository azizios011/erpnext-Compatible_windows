frappe.pages["general-ledger-setup"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("General Ledger Setup"),
		single_column: true,
	});
};
