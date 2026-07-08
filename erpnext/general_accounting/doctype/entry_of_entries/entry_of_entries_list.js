frappe.listview_settings["Entry of Entries"] = {
	add_fields: ["entry_type", "company", "posting_date", "total_debit", "total_credit", "abbr"],

	get_indicator(doc) {
		const colors = {
			Purchase: "orange",
			Sales: "blue",
		};
		return [__(doc.entry_type), colors[doc.entry_type] || "gray", "entry_type,=," + doc.entry_type];
	},

	onload(listview) {
		listview.page.add_inner_button(__("New Purchase Entry"), () => {
			frappe.route_options = { entry_type: "Purchase" };
			frappe.new_doc("Entry of Entries");
		});

		listview.page.add_inner_button(__("New Sales Entry"), () => {
			frappe.route_options = { entry_type: "Sales" };
			frappe.new_doc("Entry of Entries");
		});
	},
};
