// List view for Treasury Transaction: posting status indicator.
frappe.listview_settings["Treasury Transaction"] = {
	add_fields: ["status", "total_debit", "total_credit", "mvt"],
	refresh(listview) {
		erpnext.entries.list_totaux(listview);
	},
	get_indicator(doc) {
		if (doc.status === "Comptabilise") {
			return [__("Comptabilise"), "green", "status,=,Comptabilise"];
		}
		return [__("Brouillon"), "orange", "status,=,Brouillon"];
	},
};
