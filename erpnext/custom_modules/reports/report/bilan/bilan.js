// Bilan — the SCE balance sheet. The sections and the two grand totals read
// from the row_type; the Rubrique cells of rubrique rows are drill-down
// links into Ledger Data prefilled with the rubrique's account prefixes
// (Saisie libre); "Sans millimes" rounds every currency cell to whole dinars.
const DM_DRILL_STYLES = `
	.bilan-drill-link { color: #2563eb; cursor: pointer; text-decoration: underline; text-underline-offset: 2px; }
	.bilan-section-row .dt-cell { background-color: #f8f9fa; font-weight: 600; }
	.bilan-total-row .dt-cell { font-weight: 700; border-top: 2px solid #d1d8dd; }
`;
let bilan_styles_injected = false;

frappe.query_reports["Bilan"] = {
	filters: [
		{
			fieldname: "period_type",
			label: __("Periode"),
			fieldtype: "Select",
			options: "Mensuelle\nTrimestrielle\nAnnuelle\nPersonnalisee",
			default: "Annuelle",
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Mois"),
			fieldtype: "Select",
			options: "Janvier\nFevrier\nMars\nAvril\nMai\nJuin\nJuillet\nAout\nSeptembre\nOctobre\nNovembre\nDecembre",
			default: "Janvier",
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
		{ fieldname: "sans_millimes", label: __("Sans millimes"), fieldtype: "Check", default: 0 },
	],
	formatter(row, cell, value, column, data, default_formatter) {
		try {
			if (data && data.row_type === "rubrique" && column.fieldname === "rubrique" && data.saisie_libre) {
				return `<span class="bilan-drill-link" data-saisie-libre="${frappe.utils.escape_html(data.saisie_libre)}">${__(
					value == null ? "" : String(value)
				)}</span>`;
			}
			const rounded = frappe.query_reports["Bilan"].__sans_millimes;
			if (
				rounded &&
				data &&
				(column.fieldtype === "Currency" || column.fieldname === "variation_pct") &&
				value != null
			) {
				return Number(value).toLocaleString("fr-FR", { maximumFractionDigits: 0 });
			}
		} catch (error) {
			console.error("bilan: formatter failed", error);
		}
		return default_formatter(value, row, column, data);
	},
	onload(report) {
		if (!bilan_styles_injected) {
			$("<style>").text(DM_DRILL_STYLES).appendTo("head");
			bilan_styles_injected = true;
		}
		const apply = () => {
			frappe.query_reports["Bilan"].__sans_millimes = Boolean(report.get_filter_value("sans_millimes"));
			report.datatable && report.datatable.refresh && report.datatable.refresh();
		};
		apply();
		report.get_filter("sans_millimes").$input.on("change", apply);

		// the drill-down: a rubrique opens Ledger Data on its account prefixes
		report.$report
			.off("click.bilan-drill")
			.on("click.bilan-drill", ".bilan-drill-link", function (event) {
				event.preventDefault();
				event.stopPropagation();
				frappe.route_options = {
					ledger_type: "General",
					extract_type: "Saisie libre",
					saisie_libre: $(this).attr("data-saisie-libre"),
					period_type: "Annuelle",
				};
				frappe.set_route("query-report", "Ledger Data");
			});
	},
};
