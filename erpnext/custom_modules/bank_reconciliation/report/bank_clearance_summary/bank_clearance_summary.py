# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Bank Clearance Summary — the line view of the rapprochement bancaire,
over OUR ledger (Ecriture Comptable) for the dock context's Entreprise and
Exercice. The Report record of the same name is re-pointed to the module
"Bank Reconciliation" (custom_modules/setup.py after_migrate); no core file
under erpnext/accounts/ is touched.

Filters: type_ecriture (Toutes / Rapprochees / Non rapprochees), journal,
account, period (from_date/to_date), piece de tresorerie, date rapprochement
(exact). One row per ledger line — the same table the Rapprochement Manuel
page edits, read-only — plus a totals row and the summary cards
(Total Debit / Total Credit / Solde, 3 decimals).
"""

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext.custom_modules.bank_reconciliation.bank_statement_logic import (
    filter_line_rows,
    is_rapprochee,
    r3,
    totals,
)
from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import REPORT_CURRENCY, check_ledger_read_permission

LEDGER = "Ecriture Comptable"

TYPE_MAP = {"Rapprochees": "Rapprochee", "Non rapprochees": "Non rapprochee"}


def execute(filters=None) -> tuple:
    filters = frappe._dict(filters or {})
    context = require_context()
    check_ledger_read_permission()
    columns = get_columns()

    account = (filters.get("account") or "").strip()
    if not account:
        return columns, [], _("Pick a bank account."), None, []

    rows = _line_rows(filters, context, account)
    sums = totals(rows)
    summary = _summary(sums, rows)

    data = [_report_row(row) for row in rows]
    data.append(
        {
            "libelle": _("Total ({0} ligne(s))").format(len(rows)),
            "debit": sums["total_debit"],
            "credit": sums["total_credit"],
            "solde": sums["solde"],
            "row_type": "total",
        }
    )

    cleared_on = filters.get("date_rapprochement")
    message = (
        _("Lignes rapprochees le {0}: {1}.").format(
            getdate(cleared_on).strftime("%d/%m/%Y"),
            sum(1 for row in rows if row.get("date_rapprochement") and getdate(row["date_rapprochement"]) == getdate(cleared_on)),
        )
        if cleared_on and rows
        else None
    )
    return columns, data, message, None, summary


def _line_rows(filters: dict, context: dict, account: str) -> list[dict]:
    rows = frappe.get_all(
        LEDGER,
        filters=[
            ["entreprise", "=", context["entreprise"]],
            ["exercice", "=", context["exercice"]],
            ["account", "=", account],
        ],
        fields=[
            "name",
            "posting_date",
            "journal",
            "mvt",
            "ref_doc",
            "libelle",
            "debit",
            "credit",
            "devise",
            "tresorerie",
            "date_rapprochement",
            "rapprochement_manuel",
            "source_entry_doctype",
            "source_entry",
            "creation",
        ],
        order_by="posting_date asc, creation asc",
    )
    for row in rows:
        row["posting_date"] = getdate(row.posting_date) if row.posting_date else None
        row["date_rapprochement"] = getdate(row.date_rapprochement) if row.date_rapprochement else None

    return filter_line_rows(rows, filters)


def _report_row(row: dict) -> dict:
    cleared = row.get("date_rapprochement")
    return {
        "mvt": row.get("mvt"),
        "journal": row.get("journal"),
        "date_rapprochement": cleared.strftime("%d/%m/%Y") if cleared else "",
        "compte": row.get("account"),
        "posting_date": row.get("posting_date"),
        "tresorerie": row.get("tresorerie"),
        "libelle": row.get("libelle"),
        "debit": r3(row.get("debit")),
        "credit": r3(row.get("credit")),
        "source_entry_doctype": row.get("source_entry_doctype"),
        "source_entry": row.get("source_entry"),
        "ref_doc": row.get("ref_doc"),
        "rapprochee": 1 if is_rapprochee(row) else 0,
        "row_type": "ligne",
    }


def _summary(sums: dict, rows: list[dict]) -> list[dict]:
    cleared = sum(1 for row in rows if row.get("rapprochement_manuel"))
    return [
        {
            "label": _("Total Debit"),
            "value": sums["total_debit"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Blue",
        },
        {
            "label": _("Total Credit"),
            "value": sums["total_credit"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Blue",
        },
        {
            "label": _("Solde"),
            "value": sums["solde"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Orange" if abs(sums["solde"]) > 0.0005 else "Green",
        },
        {
            "label": _("Lignes rapprochees"),
            "value": cleared,
            "datatype": "Int",
            "indicator": "Grey",
        },
    ]


def get_columns() -> list[dict]:
    return [
        {"label": _("Mvt"), "fieldname": "mvt", "fieldtype": "Dynamic Link", "options": "source_entry_doctype", "width": 110},
        {"label": _("Jrn"), "fieldname": "journal", "fieldtype": "Link", "options": "Journal", "width": 70},
        {"label": _("Date Rappro."), "fieldname": "date_rapprochement", "fieldtype": "Data", "width": 100},
        {"label": _("Compte"), "fieldname": "compte", "fieldtype": "Link", "options": "Chart of Account", "width": 160},
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 90},
        {"label": _("Tresorerie"), "fieldname": "tresorerie", "fieldtype": "Link", "options": "Operation Tresorerie", "width": 130},
        {"label": _("Libelle"), "fieldname": "libelle", "fieldtype": "Data", "width": 220},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": REPORT_CURRENCY, "precision": "3", "width": 120},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": REPORT_CURRENCY, "precision": "3", "width": 120},
        {"label": _("N Doc"), "fieldname": "ref_doc", "fieldtype": "Data", "width": 110},
        {"label": _("Rapprochee"), "fieldname": "rapprochee", "fieldtype": "Check", "hidden": 1},
    ]
