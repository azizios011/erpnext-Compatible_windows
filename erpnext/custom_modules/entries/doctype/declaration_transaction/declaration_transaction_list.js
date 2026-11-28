// List view for Declaration Transaction: the DM workflow status.
frappe.listview_settings["Declaration Transaction"] = {
	add_fields: ["status", "mois", "type_declaration"],
	get_indicator(doc) {
		if (doc.status === "Depose") {
			return [__("Depose"), "green", "status,=,Depose"];
		}
		if (doc.status === "Cloture") {
			return [__("Cloture"), "blue", "status,=,Cloture"];
		}
		return [__("Brouillon"), "orange", "status,=,Brouillon"];
	},
};
