// Operations de Tresorerie list: Axeane-style pill tabs (Exploitation /
// Investissement / Financement with live counts), a "Changer le type"
// toggle between Societe and Personne Physique, and the relabelled add
// button prefilling categorie + type_plan from the active tab.
frappe.listview_settings["Operation Tresorerie"] = {
	hide_name_filter: true,
	onload(listview) {
		listview.__axeane_type = "Societe";
		listview.__axeane_categorie = "Exploitation";

		const set_type = (type_plan) => {
			listview.__axeane_type = type_plan;
			apply_filters(listview);
			render_tabs(listview);
		};

		const apply_filters = (refresh = true) => {
			const filters = [
				[listview.doctype, "type_plan", "=", listview.__axeane_type],
				[listview.doctype, "categorie", "=", listview.__axeane_categorie],
			];
			listview.filter_area.clear(false).then(() => listview.filter_area.add(filters, refresh));
		};

		listview.page.add_inner_button(__("Changer le type"), () => {
			set_type(listview.__axeane_type === "Societe" ? "Personne Physique" : "Societe");
		});

		// the standard Add button becomes the Axeane-labelled one, prefilled
		// with the active categorie and type
		listview.page.set_primary_action(__("Ajouter une operation"), () => {
			frappe.new_doc("Operation Tresorerie", {
				categorie: listview.__axeane_categorie,
				type_plan: listview.__axeane_type,
			});
		});

		// default view: Exploitation of the Societe type
		apply_filters(false);
		listview.filter_area
			.add(
				[
					[listview.doctype, "type_plan", "=", "Societe"],
					[listview.doctype, "categorie", "=", "Exploitation"],
				],
				false
			)
			.then(() => {
				render_tabs(listview);
			});
	},
	refresh(listview) {
		render_tabs(listview);
	},
};

function render_tabs(listview) {
	frappe.call({
		method: "erpnext.custom_modules.organization.doctype.operation_tresorerie.operation_tresorerie.get_categorie_counts",
		args: { type_plan: listview.__axeane_type || "Societe" },
		callback(r) {
			const counts = r.message || {};
			const $tabs = $("#tu-ot-tabs");
			if (!$tabs.length) {
				listview.$result.before('<div id="tu-ot-tabs" class="tu-ot-tabs" style="margin: 4px 0 8px; display: flex; gap: 6px;"></div>');
			}
			$("#tu-ot-tabs").html(
				["Exploitation", "Investissement", "Financement"]
					.map(
						(cat) =>
							`<button class="btn btn-xs btn-default tu-ot-tab ${listview.__axeane_categorie === cat ? "active" : ""}" data-cat="${cat}">
								${__(cat)} (${counts[cat] || 0})
							</button>`
					)
					.join("")
			);
			$("#tu-ot-tabs .tu-ot-tab")
				.off("click")
				.on("click", (e) => {
					listview.__axeane_categorie = $(e.currentTarget).data("cat");
					listview.filter_area.clear(false).then(() =>
						listview.filter_area.add(
							[
								[listview.doctype, "type_plan", "=", listview.__axeane_type],
								[listview.doctype, "categorie", "=", listview.__axeane_categorie],
							],
							true
						)
					);
				});
			// the title tracks the selected type
			listview.page.set_title(__("Operations de tresorerie - {0}", [listview.__axeane_type]));
		},
	});
}
