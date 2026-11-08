// List view for Receivable Transaction: posting status indicator.
frappe.listview_settings["Receivable Transaction"] = {
	add_fields: ["status", "mvt"],
	get_indicator(doc) {
		if (doc.status === "Comptabilise") {
			return [__("Comptabilise"), "green", "status,=,Comptabilise"];
		}
		return [__("Brouillon"), "orange", "status,=,Brouillon"];
	},
};
