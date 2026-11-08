// List view for RS Vente: entry-status indicator, the Axeane filter panel
// and the pen button in the row's activity cluster (shared code lives in
// facturation_entry.js).
frappe.listview_settings["RS Vente"] = {
	add_fields: ["entry_status", "entry", "entry_doctype", "mvt", "creation", "owner", "attachment", "description"],
	hide_name_filter: true,
	get_indicator(doc) {
		if (doc.entry_status === "Comptabilisee") {
			return [__("Comptabilisee"), "green", "entry_status,=,Comptabilisee"];
		}
		if (doc.entry_status === "Brouillon") {
			return [__("Brouillon"), "orange", "entry_status,=,Brouillon"];
		}
		return [__("Non saisie"), "gray", "entry_status,=,Non saisie"];
	},
	onload(listview) {
		erpnext.facturation.setup_list(listview);
	},
	refresh(listview) {
		erpnext.facturation.on_list_refresh(listview);
	},
};
