# Copyright (c) 2026, Frappe Technologies Pty. Ltd. and contributors
# For license information, please see license.txt

"""Journaux — the consultation des journaux over the Ecriture Comptable
ledger, for the dock context's Entreprise and Exercice. ONE report, three
modes through the type_journal filter:

- Detaille: the ledger lines inside the resolved period, journal and piece
  filtered, with the Total Debit / Total Credit summary cards;
- Centralise: one row per journal and month (the monthly totals of each
  journal);
- General: one row per month across all journals.

The period model is resolve_period's (clamped to the Exercice); the piece
search matches ref_doc.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import (
    REPORT_CURRENCY,
    as_list,
    check_ledger_read_permission,
    resolve_period,
)

LEDGER_DOCTYPE = "Ecriture Comptable"


def execute(filters=None) -> tuple:
    filters = filters or {}
    context = require_context()
    check_ledger_read_permission()
    from_date, to_date = resolve_period(filters, context)
    mode = filters.get("type_journal") or "Detaille"

    ledger_filters = [
        ["entreprise", "=", context["entreprise"]],
        ["exercice", "=", context["exercice"]],
        ["posting_date", ">=", from_date],
        ["posting_date", "<=", to_date],
    ]
    journals = as_list(filters.get("journal"))
    if journals:
        ledger_filters.append(["journal", "in", journals])
    ref_doc = (filters.get("ref_doc") or "").strip()
    if ref_doc:
        ledger_filters.append(["ref_doc", "like", f"%{ref_doc}%"])
    devise = (filters.get("devise") or "").strip()
    if devise:
        ledger_filters.append(["devise", "=", devise])

    if mode == "Detaille":
        rows, columns, summary = _detaille(ledger_filters)
        return columns, rows, None, None, summary
    if mode == "Centralise":
        rows, columns, summary = _centralise(ledger_filters)
        return columns, rows, None, None, summary
    rows, columns, summary = _general(ledger_filters)
    return columns, rows, None, None, summary


def _detaille(ledger_filters: list) -> tuple:
    rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters=ledger_filters,
        fields=["name", "posting_date", "journal", "mvt", "account", "libelle", "debit", "credit", "lettrage", "ref_doc", "tresorerie"],
    )
    numbers = frappe.get_all(
        "Chart of Account",
        filters={"name": ("in", {row.account for row in rows})} if rows else {"name": ""},
        fields=["name", "account_number", "account_name"],
    )
    display = {
        n.name: " ".join(x for x in (n.account_number, n.account_name) if x) or n.name for n in numbers
    }
    out = []
    for row in rows:
        out.append(
            {
                "mvt": row.mvt,
                "journal": row.journal,
                "compte": display.get(row.account, row.account),
                "posting_date": row.posting_date,
                "libelle": row.libelle,
                "tresorerie": row.tresorerie,
                "debit": flt(row.debit, 3),
                "credit": flt(row.credit, 3),
                "lettrage": row.lettrage,
                "ref_doc": row.ref_doc,
            }
        )
    out.sort(key=lambda r: (getdate(r["posting_date"]), r["journal"], r["compte"]))
    columns = [
        {"label": _("Mvt"), "fieldname": "mvt", "fieldtype": "Data", "width": 130},
        {"label": _("Jrn"), "fieldname": "journal", "fieldtype": "Data", "width": 70},
        {"label": _("Compte"), "fieldname": "compte", "fieldtype": "Data", "width": 230},
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Libelle"), "fieldname": "libelle", "fieldtype": "Data", "width": 250},
        {"label": _("Tresorerie"), "fieldname": "tresorerie", "fieldtype": "Data", "width": 130},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "precision": "3", "width": 130},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "precision": "3", "width": 130},
        {"label": _("Lettrage"), "fieldname": "lettrage", "fieldtype": "Data", "width": 90},
        {"label": _("N Doc"), "fieldname": "ref_doc", "fieldtype": "Data", "width": 120},
    ]
    return out, columns, _summary(out)


def _centralise(ledger_filters: list) -> tuple:
    rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters=ledger_filters,
        fields=["journal", "mois", "debit", "credit"],
    )
    totals: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.journal or "", str(cint(row.mois) or 0).zfill(2))
        entry = totals.setdefault(key, {"debit": 0.0, "credit": 0.0})
        entry["debit"] = flt(entry["debit"] + flt(row.debit), 3)
        entry["credit"] = flt(entry["credit"] + flt(row.credit), 3)
    out = [
        {
            "journal": journal,
            "mois": mois,
            "debit": flt(entry["debit"], 3),
            "credit": flt(entry["credit"], 3),
        }
        for (journal, mois), entry in sorted(totals.items())
    ]
    columns = [
        {"label": _("Journal"), "fieldname": "journal", "fieldtype": "Data", "width": 140},
        {"label": _("Mois"), "fieldname": "mois", "fieldtype": "Select", "width": 80},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "precision": "3", "width": 160},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "precision": "3", "width": 160},
    ]
    return out, columns, _summary(out)


def _general(ledger_filters: list) -> tuple:
    rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters=ledger_filters,
        fields=["mois", "debit", "credit"],
    )
    totals: dict[str, dict] = {}
    for row in rows:
        mois = str(cint(row.mois) or 0).zfill(2)
        entry = totals.setdefault(mois, {"debit": 0.0, "credit": 0.0})
        entry["debit"] = flt(entry["debit"] + flt(row.debit), 3)
        entry["credit"] = flt(entry["credit"] + flt(row.credit), 3)
    out = [
        {"mois": mois, "debit": flt(entry["debit"], 3), "credit": flt(entry["credit"], 3)}
        for mois, entry in sorted(totals.items())
    ]
    columns = [
        {"label": _("Mois"), "fieldname": "mois", "fieldtype": "Select", "width": 120},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "precision": "3", "width": 200},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "precision": "3", "width": 200},
    ]
    return out, columns, _summary(out)


def _summary(rows: list[dict]) -> list[dict]:
    total_debit = flt(sum(flt(r["debit"]) for r in rows), 3)
    total_credit = flt(sum(flt(r["credit"]) for r in rows), 3)
    solde = flt(total_debit - total_credit, 3)
    return [
        {"label": _("Total Debit"), "value": total_debit, "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Green"},
        {"label": _("Total Credit"), "value": total_credit, "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Red"},
        {"label": _("Solde"), "value": solde, "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Blue"},
    ]
