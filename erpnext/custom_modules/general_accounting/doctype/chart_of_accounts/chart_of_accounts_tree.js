frappe.treeview_settings["Chart of Accounts"] = {
	get_tree_root: true,
	root_label: "Chart of Accounts",
	get_tree_nodes: "erpnext.custom_modules.general_accounting.doctype.chart_of_accounts.chart_of_accounts.get_children",
};
