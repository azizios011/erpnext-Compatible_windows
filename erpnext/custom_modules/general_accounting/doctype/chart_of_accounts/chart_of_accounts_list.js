frappe.listview_settings["Chart of Accounts"] = {
	hide_name_column: true,
	onload: function (listview) {
		listview.set_primary_action = function () {
			listview.page.clear_primary_action();
		};
		listview.set_primary_action();

		listview.settings.button = {
			show: () => true,
		};

		listview.generate_button_html = function (doc) {
			return `<div class="list-row-col hidden-xs coa-row-actions">
				<button class="btn btn-xs btn-default coa-row-add" data-name="${doc.name}" title="${__("New Account")}">${frappe.utils.icon("plus", "sm")}</button>
				<button class="btn btn-xs btn-default coa-row-delete" style="margin-left: 4px;" data-name="${doc.name}" title="${__("Delete")}">${frappe.utils.icon("delete", "xs")}</button>
			</div>`;
		};

		listview.$result.on("click", ".coa-row-add", function (e) {
			e.preventDefault();
			e.stopPropagation();
			listview.new_doc();
		});

		listview.$result.on("click", ".coa-row-delete", function (e) {
			e.preventDefault();
			e.stopPropagation();
			let name = $(this).attr("data-name");
			frappe.confirm(__("Delete account {0}?", [name]), () => {
				frappe.db.delete_doc("Chart of Accounts", name).then(() => listview.refresh());
			});
		});
	},
};

