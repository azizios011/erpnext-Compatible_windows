frappe.pages["states"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("States"),
		single_column: true,
	});
};
