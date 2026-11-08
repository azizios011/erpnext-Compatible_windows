// Entreprises list: Axeane columns, status/param-paie indicators, the
// Utilisateurs bubbles and the "Suivi Creation" toolbar filter.
frappe.listview_settings["Entreprise"] = {
	add_fields: ["status", "param_paie", "nb_utilisateurs", "utilisateurs_json", "code", "raison_sociale"],
	hide_name_filter: true,
	get_indicator(doc) {
		if (doc.status === "Creee") {
			return [__("CREEE"), "green", "status,=,Creee"];
		}
		return [__("EN CREATION"), "orange", "status,=,En creation"];
	},
	formatters: {
		param_paie(value) {
			if (value === "TERMINE") {
				return `<span class="indicator-pill green">${__("TERMINE")}</span>`;
			}
			return `<span class="indicator-pill gray">${__("Non parametre")}</span>`;
		},
		utilisateurs_json(value, df, doc) {
			let users = [];
			try {
				users = JSON.parse(doc.utilisateurs_json || "[]");
			} catch (error) {
				users = [];
			}
			const avatars = users
				.slice(0, 2)
				.map((user) =>
					frappe.ui.avatar({
							label: frappe.user_info(user).fullname,
							image: frappe.user_info(user).image,
							size: "xs",
						})
				)
				.join(" ");
			const count = doc.nb_utilisateurs || users.length;
			return `${avatars} <span class="text-muted">${frappe.utils.icon("users", "xs")} ${count}</span>`;
		},
	},
	onload(listview) {
		listview.page.add_inner_button(__("Suivi Creation"), () => {
			listview.filter_area.add(listview.doctype, "status", "=", "En creation");
		});
	},
};
