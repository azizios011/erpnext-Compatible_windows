# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Bank Reconciliation Statement — the balance view of the rapprochement
bancaire, over OUR ledger (Ecriture Comptable) for the dock context's
Entreprise and Exercice.

The Report record of the same name is re-pointed to the module
"Bank Reconciliation" (custom_modules/setup.py after_migrate) so this file
serves instead of erpnext/accounts/report/... — the frappe fork resolves
both the execute import and the served .js through the custom-modules map;
no core file is touched.

ERPNext's statement layout, our labels and our ledger:

    Solde initial (releve au …)            Solde Initial Banque, signed by
                                             its sens (reference row)
    Solde comptable au …                   sum(debit - credit) up to the
                                             date
    —
    Cheques emis non rapproches (credits)  book credits not yet cleared
    Encaissements non rapproches (debits)  book debits not yet cleared
    —
    Solde releve theorique au …            comptable - encaissements +
                                             cheques (erpnext's
                                             "Calculated Bank Statement
                                             balance": balance - total_debit
                                             + total_credit)

The core's "amounts not reflected in system" row (entries posted after the
date but cleared before it) has no equivalent here: rapprochement only
marks existing ledger rows, and such a skew is surfaced by the ecart the
accountant reads against the paper releve.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from erpnext.custom_modules.bank_reconciliation.bank_statement_logic import compute_statement
from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import (
    MONTHS_FR,
    REPORT_CURRENCY,
    check_ledger_read_permission,
)

LEDGER = "Ecriture Comptable"


def execute(filters=None) -> tuple:
    filters = frappe._dict(filters or {})
    context = require_context()
    check_ledger_read_permission()

    account = (filters.get("account") or "").strip()
    report_date = getdate(filters.get("report_date") or nowdate())

    if not account:
        return _columns(), [], _("Pick a bank account."), None, []

    rows = _ledger_rows(context, account)
    initial = _solde_initial(context, account)
    statement = compute_statement(rows, report_date, solde_initial=initial["signed"] if initial else None)

    data = [
        _balance_row(
            _("Solde initial (releve {0})").format(_mois_label(initial["mois"], context)) if initial
            else _("Solde initial (releve): non defini"),
            statement["solde_initial"],
        ),
        {},
        _balance_row(_("Solde comptable au {0}").format(_fmt_date(report_date)), statement["solde_comptable"]),
        {},
        {
            "statement_line": _("Cheques emis non rapproches (credits): {0} ligne(s)").format(
                statement["count_credit_non_rapprochees"]
            ),
            "credit": statement["cheques_emis_non_rapproches"],
        },
        {
            "statement_line": _("Encaissements non rapproches (debits): {0} ligne(s)").format(
                statement["count_debit_non_rapprochees"]
            ),
            "debit": statement["encaissements_non_rapproches"],
        },
        {},
        _balance_row(
            _("Solde releve theorique au {0}").format(_fmt_date(report_date)),
            statement["solde_releve_theorique"],
        ),
    ]

    message = None
    if not initial:
        message = _(
            "Aucun Solde Initial Banque pour ce compte: saisissez-le depuis la page Rapprochement Manuel."
        )
    summary = [
        {
            "label": _("Solde initial (releve)"),
            "value": statement["solde_initial"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Grey",
        },
        {
            "label": _("Solde comptable"),
            "value": statement["solde_comptable"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Blue",
        },
        {
            "label": _("Non rapproche (net)"),
            "value": statement["encaissements_non_rapproches"] - statement["cheques_emis_non_rapproches"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Orange",
        },
        {
            "label": _("Solde releve theorique"),
            "value": statement["solde_releve_theorique"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Green",
        },
    ]
    return _columns(), data, message, None, summary


def _ledger_rows(context: dict, account: str) -> list[dict]:
    return frappe.get_all(
        LEDGER,
        filters=[
            ["entreprise", "=", context["entreprise"]],
            ["exercice", "=", context["exercice"]],
            ["account", "=", account],
        ],
        fields=["posting_date", "debit", "credit", "rapprochement_manuel", "date_rapprochement"],
        order_by="posting_date asc, creation asc",
    )


def _solde_initial(context: dict, account: str) -> dict | None:
    row = frappe.db.get_value(
        "Solde Initial Banque",
        {"entreprise": context["entreprise"], "exercice": context["exercice"], "account": account},
        ["solde_initial", "mois", "sens"],
        as_dict=True,
    )
    if not row:
        return None
    signed = float(row.solde_initial or 0)
    if (row.sens or "Debit") == "Credit":
        signed = -signed
    return {"signed": signed, "mois": row.mois, "sens": row.sens}


def _balance_row(label: str, amount: float | None) -> dict:
    """erpnext's get_balance_row: a positive balance reads Debit, a negative
    one reads Credit — the bank account's natural side."""
    value = amount or 0
    if value >= 0:
        return {"statement_line": label, "debit": value, "credit": 0}
    return {"statement_line": label, "debit": 0, "credit": -value}


def _mois_label(mois: str | None, context: dict) -> str:
    if mois in MONTHS_FR:
        year = getdate(context.get("date_debut")).year if context.get("date_debut") else ""
        return f"{mois} {year}".strip()
    return _("au {0}").format(_fmt_date(getdate(context.get("date_debut")))) if context.get("date_debut") else ""


def _fmt_date(value) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def _columns() -> list[dict]:
    return [
        {"label": _("Statement"), "fieldname": "statement_line", "fieldtype": "Data", "width": 420},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "options": REPORT_CURRENCY, "precision": "3", "width": 150},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "options": REPORT_CURRENCY, "precision": "3", "width": 150},
    ]
