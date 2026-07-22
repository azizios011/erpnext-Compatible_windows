frappe.pages["bank-reconciliation"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Bank reconciliation"),
		single_column: true,
	});
};
