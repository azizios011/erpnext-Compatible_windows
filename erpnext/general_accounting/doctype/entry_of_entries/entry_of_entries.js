frappe.ui.form.on('Entry of Entries', {
    setup(frm) {
        frm.set_query('abbr', () => ({}));
    },
    onload(frm) {
        if (frm.is_new() && frappe.route_options?.entry_type && !frm.doc.entry_type) {
            frm.set_value('entry_type', frappe.route_options.entry_type);
        }
    },
    refresh(frm) {
        calculate_totals(frm);
        if (frm.is_new()) {
            set_treatments_breadcrumbs(__("New Entry of Entries"));
        } else {
            set_treatments_breadcrumbs(frm.doc.name);
        }
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

function set_treatments_breadcrumbs(leaf_label) {
    setTimeout(() => {
        frappe.breadcrumbs.clear();
        frappe.breadcrumbs.append_breadcrumb_element(
            get_treatments_route(),
            __("Treatments"),
            "worksapce-breadcrumb"
        );
        frappe.breadcrumbs.append_breadcrumb_element("", leaf_label);
        $("body").addClass("no-breadcrumbs");
    }, 100);
}

function get_treatments_route() {
    if (frappe.utils.get_desktop_icon_by_label) {
        const icon = frappe.utils.get_desktop_icon_by_label("Treatments");
        if (icon) {
            return frappe.utils.get_route_for_icon(icon) || "/desk/treatments";
        }
    }
    return "/desk/treatments";
}
