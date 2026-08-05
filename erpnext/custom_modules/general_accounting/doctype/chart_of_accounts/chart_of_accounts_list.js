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
				<button class="btn btn-xs btn-default coa-row-delete" style="margin-left: 4px;" data-name="${doc.name}" title="${__("Delete")}">${frappe.utils.icon("trash-2", "xs")}</button>
			</div>`;
		};

		listview.get_meta_html = function () {
			return "";
		};

		listview.get_header_html_skeleton = function (left = "") {
			return `
			<div class="list-row-container">
				<header class="level list-row-head text-muted">
					<div class="level-left list-header-subject">
						${left}
					</div>
					<div class="level-left checkbox-actions">
						<div class="level list-subject">
							<span class="level-item select-like">
								<input class="list-header-checkbox list-check-all" type="checkbox" title="${__("Select All")}">
							</span>
							<span class="level-item list-header-meta"></span>
						</div>
					</div>
				</header>
			</div>
			`;
		};

		const original_get_header_html = listview.get_header_html.bind(listview);
		listview.get_header_html = function () {
			let html = original_get_header_html();
			html = html.replace(
				'<div class="list-row-col hidden-xs"></div>',
				`<div class="list-row-col hidden-xs">${__("Edition")}</div>`
			);
			return html;
		};

		listview.get_list_row_html_skeleton = function (left = "", { virtual = false } = {}) {
			const virtual_attr = virtual ? ' data-virtual-row="1"' : "";
			return `
				<div class="list-row-container" tabindex="1"${virtual_attr}>
					<div class="level list-row">
						<div class="level-left ellipsis">
							${left}
						</div>
					</div>
				</div>
			`;
		};

		listview.$result.on("click", ".coa-row-add", function (e) {
			e.preventDefault();
			e.stopPropagation();
			listview.make_new_doc();
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

