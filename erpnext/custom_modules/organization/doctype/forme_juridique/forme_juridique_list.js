// Forme Juridique list: the import hub entry point (the master data
// doctypes import from xlsx through the shared Import Configuration dialog).
frappe.listview_settings["Forme Juridique"] = {
	onload(listview) {
		listview.page.add_menu_item(__("Importer"), () => {
			erpnext.import_hub.open_dialog("Forme Juridique", { on_import: () => listview.refresh() });
		});
	},
};
