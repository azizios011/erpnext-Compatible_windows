// erpnext/tunisian_accounting/doctype/chart_of_accounts/chart_of_accounts.js

// Auto-redirect list view to tree view.
frappe.listview_settings["Chart of Accounts"] = {
	onload: function () {
		frappe.set_route("Tree", "Chart of Accounts");
	},
};

frappe.treeview_settings["Chart of Accounts"] = {
	breadcrumb: "Config",
	title: __("Plan Comptable - Tunisie"),
	get_tree_nodes:
		"erpnext.tunisian_accounting.doctype.chart_of_accounts.chart_of_accounts.get_children",

	// What to show next to each node in the tree
	get_label: function (node) {
		if (node.data.account_number) {
			return `<span class="text-muted" style="font-size:11px; margin-right:6px;">${node.data.account_number}</span>${node.data.title}`;
		}
		return node.data.title;
	},

	// Toolbar buttons shown when a node is selected
	toolbar: [
		{
			label: __("Add Child"),
			click: function (node) {
				frappe.new_doc("Chart of Accounts", {
					parent_chart_of_accounts: node.data.value,
					is_group: 0,
				});
			},
			btnClass: "hidden-xs",
		},
		{
			label: __("Edit"),
			click: function (node) {
				frappe.set_route("Form", "Chart of Accounts", node.data.value);
			},
		},
	],

	// Colour-code root types for quick visual orientation
	onrender: function (node) {
		const colours = {
			Asset: "#2490EF",
			Liability: "#E24C4C",
			Equity: "#7B61FF",
			Income: "#28A745",
			Expense: "#F39C12",
		};
		if (node.data.root_type && colours[node.data.root_type]) {
			$(node.li)
				.find(".tree-label")
				.css("border-left", `3px solid ${colours[node.data.root_type]}`)
				.css("padding-left", "6px");
		}
	},

	// Show sens badge (D / C / DC) as extra info
	get_tooltip: function (node) {
		const parts = [];
		if (node.data.account_type) parts.push(__("Type: {0}", [node.data.account_type]));
		if (node.data.sens) parts.push(__("Sens: {0}", [node.data.sens]));
		return parts.join(" | ");
	},
};
