// List view for Facture Achat: entry-status indicator + per-row pen button
// (opens the stage-2 Entries form; see facturation_entry.js)
frappe.listview_settings["Facture Achat"] = {
	add_fields: ["entry_status", "entry", "entry_doctype", "mvt"],
	get_indicator(doc) {
		if (doc.entry_status === "Comptabilisee") {
			return [__("Comptabilisee"), "green", "entry_status,=,Comptabilisee"];
		}
		if (doc.entry_status === "Brouillon") {
			return [__("Brouillon"), "orange", "entry_status,=,Brouillon"];
		}
		return [__("Non saisie"), "gray", "entry_status,=,Non saisie"];
	},
	button: {
		show(doc) {
			return !doc.__deleted;
		},
		get_label() {
			return frappe.utils.icon("square-pen", "xs");
		},
		get_description() {
			return __("Saisie ecriture");
		},
		action(doc) {
			erpnext.facturation.open_entry(doc.doctype, doc.name);
		},
	},
};
