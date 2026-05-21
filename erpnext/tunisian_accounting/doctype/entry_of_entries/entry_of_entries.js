frappe.ui.form.on('Entry of Entries', {
    setup(frm) {
        frm.set_query('abbr', 'accounting_entries', () => ({}));
    },
    refresh(frm) {
        calculate_totals(frm);
    }
});

frappe.ui.form.on('Entry of Entries Detail', {
    debit(frm) { calculate_totals(frm); },
    credit(frm) { calculate_totals(frm); },
    accounting_entries_remove(frm) { calculate_totals(frm); }
});

function calculate_totals(frm) {
    let total_debit = 0;
    let total_credit = 0;
    (frm.doc.accounting_entries || []).forEach(row => {
        total_debit += row.debit || 0;
        total_credit += row.credit || 0;
    });
    frm.set_value('total_debit', total_debit);
    frm.set_value('total_credit', total_credit);
}
