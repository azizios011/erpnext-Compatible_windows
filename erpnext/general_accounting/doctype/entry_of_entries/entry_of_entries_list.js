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
		listview.page.clear_primary_action();
		set_treatments_breadcrumbs(__("Entry of Entries"));
	},
};

function set_treatments_breadcrumbs(leaf_label) {
	setTimeout(() => {
		frappe.breadcrumbs.clear();
		frappe.breadcrumbs.append_breadcrumb_element(
			get_treatments_route(),
			__("Treatments"),
			"worksapce-breadcrumb"
		);
		frappe.breadcrumbs.append_breadcrumb_element("", leaf_label);
		$("body").addClass("no-breadcrumbs");
	}, 100);
}

function get_treatments_route() {
	if (frappe.utils.get_desktop_icon_by_label) {
		const icon = frappe.utils.get_desktop_icon_by_label("Treatments");
		if (icon) {
			return frappe.utils.get_route_for_icon(icon) || "/desk/treatments";
		}
	}
	return "/desk/treatments";
}
