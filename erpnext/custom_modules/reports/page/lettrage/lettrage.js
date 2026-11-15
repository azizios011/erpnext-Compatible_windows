// Lettrage — classic Page hosting the lettrage tool (lettrage.bundle.js).
// The tool fills the whole page; every query is scoped server-side by the
// dock context, so the title carries the context and the tool re-renders
// when the dock switches Entreprise/Exercice.
frappe.pages["lettrage"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Lettrage"),
		single_column: true,
	});

	const set_context_title = () => {
		const ctx = (window.axeane && axeane.context && axeane.context.get()) || {};
		const parts = [ctx.entreprise_label || ctx.entreprise, ctx.exercice_label || ctx.exercice].filter(
			Boolean
		);
		if (parts.length) {
			page.set_title(__("Lettrage") + " · " + parts.join(" · "));
		}
	};
	set_context_title();

	erpnext.lettrage.render({ $container: page.main, page: page });

	// a dock context change re-renders the tool (the bundle binds its own
	// data refresh); the page only keeps the title in sync
	$(document)
		.off("axeane-context-changed.lettrage-page")
		.on("axeane-context-changed.lettrage-page", () => {
			set_context_title();
		});
};
