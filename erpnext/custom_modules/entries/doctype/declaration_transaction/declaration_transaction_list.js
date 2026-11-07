// List view for Declaration Transaction: posting status indicator.
frappe.listview_settings["Declaration Transaction"] = {
	add_fields: ["status", "total_debit", "total_credit", "mvt"],
	get_indicator(doc) {
		if (doc.status === "Comptabilise") {
			return [__("Comptabilise"), "green", "status,=,Comptabilise"];
		}
		return [__("Brouillon"), "orange", "status,=,Brouillon"];
	},
};
