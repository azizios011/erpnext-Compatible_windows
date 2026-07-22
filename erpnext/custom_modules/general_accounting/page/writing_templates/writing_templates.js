frappe.pages["writing-templates"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Writing Templates"),
		single_column: true,
	});
};
