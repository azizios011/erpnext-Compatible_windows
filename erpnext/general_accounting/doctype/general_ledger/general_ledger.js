// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// License: GNU General Public License v3. See license.txt

const MONTHS = [
	"Janvier",
	"Février",
	"Mars",
	"Avril",
	"Mai",
	"Juin",
	"Juillet",
	"Août",
	"Septembre",
	"Octobre",
	"Novembre",
	"Décembre",
];

frappe.ui.form.on("General Ledger", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.fiscal_year) {
			frm.set_value("fiscal_year", String(new Date().getFullYear()));
			frm.set_value("month", MONTHS[new Date().getMonth()]);
		}
	},

	setup(frm) {
		frm.set_query("account", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
			},
		}));

		frm.set_query("journal_code", () => ({
			filters: {
				company: frm.doc.company,
			},
		}));
	},

	refresh(frm) {
		frm.page.set_primary_action(__("Afficher"), () => load_ledger_entries(frm));
		toggle_month_visibility(frm);
	},

	company(frm) {
		frm.set_value("account", "");
		frm.set_value("journal_code", "");
	},

	period_type(frm) {
		toggle_month_visibility(frm);
	},

	fiscal_year(frm) {
		update_period_dates(frm);
	},

	month(frm) {
		update_period_dates(frm);
	},
});

function toggle_month_visibility(frm) {
	const show_month = frm.doc.period_type !== "Annuelle";
	frm.toggle_display("month", show_month);
	if (!show_month) {
		frm.set_value("month", "");
	}
	update_period_dates(frm);
}

function update_period_dates(frm) {
	if (!frm.doc.fiscal_year || !frm.doc.period_type) {
		return;
	}

	if (frm.doc.period_type === "Annuelle") {
		frm.set_value("from_date", `${frm.doc.fiscal_year}-01-01`);
		frm.set_value("to_date", `${frm.doc.fiscal_year}-12-31`);
		return;
	}

	if (!frm.doc.month) {
		return;
	}

	const month_index = MONTHS.indexOf(frm.doc.month);
	if (month_index < 0) {
		return;
	}

	const year = parseInt(frm.doc.fiscal_year, 10);
	const month = month_index + 1;
	const last_day = new Date(year, month, 0).getDate();
	frm.set_value("from_date", `${year}-${String(month).padStart(2, "0")}-01`);
	frm.set_value(
		"to_date",
		`${year}-${String(month).padStart(2, "0")}-${String(last_day).padStart(2, "0")}`
	);
}

function load_ledger_entries(frm) {
	if (!frm.doc.company || !frm.doc.fiscal_year || !frm.doc.period_type) {
		frappe.msgprint(__("Please set Company, Exercice, and Période."));
		return;
	}

	if (frm.doc.period_type !== "Annuelle" && !frm.doc.month) {
		frappe.msgprint(__("Please select a month."));
		return;
	}

	if (frm.doc.extract_type === "Compte sélectionné" && !frm.doc.account) {
		frappe.msgprint(__("Please select a Compte for the chosen Type Extrait."));
		return;
	}

	frappe.call({
		method: "erpnext.general_accounting.doctype.general_ledger.general_ledger.get_entries",
		args: {
			company: frm.doc.company,
			fiscal_year: frm.doc.fiscal_year,
			period_type: frm.doc.period_type,
			month: frm.doc.month,
			from_date: frm.doc.from_date,
			to_date: frm.doc.to_date,
			account: frm.doc.account,
			journal_code: frm.doc.journal_code,
			voucher_filter: frm.doc.voucher_filter,
			ledger_type: frm.doc.ledger_type,
			extract_type: frm.doc.extract_type,
		},
		freeze: true,
		callback(r) {
			const data = r.message || {};
			frm.clear_table("entries");
			(data.entries || []).forEach((row) => {
				const entry = frm.add_child("entries");
				Object.assign(entry, row);
			});
			frm.set_value("from_date", data.from_date);
			frm.set_value("to_date", data.to_date);
			frm.set_value("total_debit", data.total_debit || 0);
			frm.set_value("total_credit", data.total_credit || 0);
			frm.set_value("balance", data.balance || 0);
			frm.refresh_field("entries");
			frm.refresh_fields(["total_debit", "total_credit", "balance", "from_date", "to_date"]);

			if (!data.entries?.length) {
				frappe.msgprint(
					__(
						"No submitted Entry of Entries found for this period. Save and submit invoices under Treatments first."
					)
				);
			}
		},
	});
}
