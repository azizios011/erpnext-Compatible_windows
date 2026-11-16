// Balance generale — the trial balance per account. The view switcher
// (PDF / List / XLSX) and the bottom summary bar come from the shared
// erpnext.reports.setup_views; the PDF and XLSX views are placeholders for
// the OnlyOffice-based previews. Scoped to the dock context like Ledger
// Data; the account set follows the balance type and the number range.
frappe.query_reports["Balance"] = {
	filters: [
		{
			fieldname: "balance_type",
			label: __("Type balance"),
			fieldtype: "Select",
			options: "General\nAuxiliaire Client\nAuxiliaire Fournisseur",
			default: "General",
			reqd: 1,
		},
		{
			fieldname: "period_type",
			label: __("Periode"),
			fieldtype: "Select",
			options: "Mensuelle\nTrimestrielle\nAnnuelle\nPersonnalisee",
			default: "Mensuelle",
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Mois"),
			fieldtype: "Select",
			options: "Janvier\nFevrier\nMars\nAvril\nMai\nJuin\nJuillet\nAout\nSeptembre\nOctobre\nNovembre\nDecembre",
			default: "Janvier",
			reqd: 1,
			depends_on: "eval:doc.period_type == 'Mensuelle'",
		},
		{
			fieldname: "quarter",
			label: __("Trimestre"),
			fieldtype: "Select",
			options: "T1\nT2\nT3\nT4",
			default: "T1",
			depends_on: "eval:doc.period_type == 'Trimestrielle'",
		},
		{
			fieldname: "from_date",
			label: __("Du"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
		},
		{
			fieldname: "to_date",
			label: __("Au"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			depends_on: "eval:doc.period_type == 'Personnalisee'",
		},
		{
			fieldname: "devise",
			label: __("Devise"),
			fieldtype: "Link",
			options: "Currency",
			default: "TND",
		},
		{
			fieldname: "extract_type",
			label: __("Type Extrait"),
			fieldtype: "Select",
			options: "Tous les comptes\nComptes mouvementes\nComptes non soldes",
			default: "Tous les comptes",
			reqd: 1,
		},
		{
			fieldname: "account_from",
			label: __("Compte de"),
			fieldtype: "Data",
			description: __("Account number range start"),
		},
		{
			fieldname: "account_to",
			label: __("Compte a"),
			fieldtype: "Data",
			description: __("Account number range end"),
		},
	],

	onload(report) {
		// the context defines the period: default month = the current month
		// when it falls inside the Exercice, else the Exercice's first month
		const context = (window.axeane && axeane.context && axeane.context.get()) || {};
		if (context.date_debut) {
			const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
			const debut = frappe.datetime.str_to_obj(context.date_debut);
			const fin = context.date_fin ? frappe.datetime.str_to_obj(context.date_fin) : null;
			const inside = debut <= today && (!fin || today <= fin);
			const month = inside ? today.getMonth() : debut.getMonth();
			const month_filter = report.get_filter("month");
			if (month_filter) {
				month_filter.df.default = GL_MONTHS[month];
				month_filter.set_input(GL_MONTHS[month]);
			}
		}

		// the title carries the context: "MEDDEB · EX 2026"
		const set_title = () => {
			const ctx = (window.axeane && axeane.context && axeane.context.get()) || {};
			if (ctx.entreprise_label || ctx.exercice_label) {
				report.page.set_title(
					__("Balance") +
						" · " +
						[ctx.entreprise_label, ctx.exercice_label].filter(Boolean).join(" · ")
				);
			}
		};
		set_title();

		$(document)
			.off("axeane-context-changed.balance")
			.on("axeane-context-changed.balance", () => {
				set_title();
			});

		// the view switcher + the bottom summary (shared with Ledger Data).
		// Optional: a failure is logged and surfaced, the report stays
		try {
			erpnext.reports.setup_views(report, {
				report_name: "Balance",
				views: {
					pdf: {
						mount(el) {
							el.innerHTML = "";
							el.appendChild(
								frappe.ui.empty_state({
									icon: "file-text",
									title: __("Apercu PDF, bientot disponible"),
									description: __("The PDF preview will be generated from the XLSX view."),
								})
							);
						},
						unmount() {},
					},
					xlsx: {
						mount(el) {
							el.innerHTML = "";
							el.appendChild(
								frappe.ui.empty_state({
									icon: "table",
									title: __("XLSX view, coming soon"),
									description: __("The XLSX view will be generated from the same data."),
								})
							);
						},
						unmount() {},
					},
				},
			});
		} catch (error) {
			console.error("report_views: setup_views failed", error);
			frappe.show_alert({
				message: __("Les vues PDF / XLSX n'ont pas pu etre chargees"),
				indicator: "orange",
			});
		}
	},
};

const GL_MONTHS = [
	"Janvier",
	"Fevrier",
	"Mars",
	"Avril",
	"Mai",
	"Juin",
	"Juillet",
	"Aout",
	"Septembre",
	"Octobre",
	"Novembre",
	"Decembre",
];
