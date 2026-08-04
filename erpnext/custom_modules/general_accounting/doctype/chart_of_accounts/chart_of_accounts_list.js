frappe.listview_settings["Chart of Accounts"] = {
	hide_name_column: true,
	onload: function (listview) {
		listview.page.set_primary_action(__("Add Account"), function () {
			listview.new_doc();
		});
	},
};

