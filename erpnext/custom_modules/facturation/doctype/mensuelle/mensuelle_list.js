// List view for Mensuelle: Période, Réf, Statut, Contrôle, Total déclaré —
// the indicator pill carries the CHECK status colours. The pen action is the
// shared Facturation one: it opens the month's Declaration Transaction.
frappe.listview_settings["Mensuelle"] = {
	...erpnext.facturation.list_settings("Mensuelle"),
	add_fields: [
		"check_status",
		"declared_total",
		"period_month",
		"period_year",
		"entry_status",
		"entry",
		"entry_doctype",
	],
	get_indicator(doc) {
		if (doc.check_status === "Ecarts") {
			return [__("Ecarts"), "red", "check_status,=,Ecarts"];
		}
		if (doc.check_status === "Avertissements") {
			return [__("Avertissements"), "orange", "check_status,=,Avertissements"];
		}
		if (doc.check_status === "Conforme") {
			return [__("Conforme"), "green", "check_status,=,Conforme"];
		}
		return [__("Non verifie"), "gray", "check_status,=,Non verifie"];
	},
};
