# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Rapprochement bancaire — the WRITE endpoints (the Bank workspace).

The read side is the two routed reports (Bank Reconciliation Statement,
Bank Clearance Summary) + rapprochement_api.lignes for the Rapprochement
Manuel page; this module owns everything that writes:

- rapprocher(ecriture_names, date_rapprochement)  — mark ledger rows cleared
- de_rapprocher(ecriture_names)                   — clear the mark
- set_solde_initial(account, solde_initial, mois, sens) — the statement-side
  opening of one bank account (Solde Initial Banque, one row per
  Exercice + Compte)
- lignes(filters) — the page's read (multi-select table + footer totals)

Rules (same gates as the rest of the product):
- Entreprise/Exercice NEVER come from the client: require_context();
- the Exercice must be Ouvert (validate_exercice_open);
- Accounts User / Accounts Manager / System Manager only;
- ONLY bank-journal rows: every touched Ecriture Comptable's journal must
  be a Banque journal (journal_type == "Banque");
- reconciliation writes touch date_rapprochement + rapprochement_manuel
  ONLY — never debit/credit — and deliberately skip the ledger lock
  (entries.ledger_lock): a row inside a clotured Déclaration Mensuelle
  keeps its amounts, only its clearing stamp moves;
- pointage (lettrage_api.toggle_pointe) stays a separate flag; the two
  features do not share fields.
"""

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from erpnext.custom_modules.organization.context import (
    require_context,
    validate_date_in_exercice,
    validate_exercice_open,
)
from erpnext.custom_modules.reports.lettrage_api import LETTRAGE_ROLES
from erpnext.custom_modules.reports.report_common import MONTHS_FR

LEDGER = "Ecriture Comptable"
BANK_JOURNAL_TYPE = "Banque"


# ── gates ────────────────────────────────────────────────────────────────────


def _check_write() -> None:
    if frappe.session.user == "Administrator":
        return
    if not set(LETTRAGE_ROLES) & set(frappe.get_roles()):
        frappe.throw(_("Not permitted to reconcile the ledger"), frappe.PermissionError)


def _context() -> dict[str, Any]:
    context = require_context()
    validate_exercice_open(context)
    return context


def _parse_names(ecriture_names: str | list) -> list[str]:
    if isinstance(ecriture_names, str):
        try:
            names = json.loads(ecriture_names or "[]")
        except ValueError:
            names = [n.strip() for n in ecriture_names.split(",") if n.strip()]
    else:
        names = list(ecriture_names or [])
    names = [str(n) for n in names if str(n).strip()]
    if not names:
        frappe.throw(_("No ledger lines selected."))
    return names


def _fetch_rows(names: list[str], context: dict[str, Any]) -> list[frappe._dict]:
    """Context-scoped rows only: names outside the Entreprise/Exercice
    vanish here, and the caller refuses partial scopes (a stray name must
    never mark the wrong entreprise's row)."""
    return frappe.get_all(
        LEDGER,
        filters=[
            ["entreprise", "=", context["entreprise"]],
            ["exercice", "=", context["exercice"]],
            ["name", "in", names],
        ],
        fields=["name", "account", "journal", "debit", "credit", "date_rapprochement", "rapprochement_manuel"],
        order_by="posting_date asc, creation asc",
    )


def _assert_bank_journal_rows(rows: list) -> None:
    """Every reconciled line belongs to a Banque journal — the rapprochement
    only ever clears treasury movements."""
    journals = {row.journal for row in rows if row.journal}
    types = {
        row.name: row.journal_type
        for row in frappe.get_all(
            "Journal",
            filters={"name": ("in", journals)} if journals else {"name": ""},
            fields=["name", "journal_type"],
        )
    }
    offenders = sorted({row.name for row in rows if types.get(row.journal) != BANK_JOURNAL_TYPE})
    if offenders:
        frappe.throw(
            _("Le rapprochement ne concerne que les ecritures de journaux de banque ({0}).").format(
                ", ".join(frappe.bold(name) for name in offenders[:5])
            )
        )


def _is_bank_account(account: str, context: dict[str, Any]) -> bool:
    """A bank account: typed Bank, or carrying Banque-journal rows in this
    exercice (some charts leave the 53x/51x account_type blank)."""
    if not account:
        return False
    account_type = frappe.db.get_value("Chart of Account", account, "account_type")
    if account_type == "Bank":
        return True
    return bool(
        frappe.get_all(
            LEDGER,
            filters=[
                ["entreprise", "=", context["entreprise"]],
                ["exercice", "=", context["exercice"]],
                ["account", "=", account],
                ["journal", "in", frappe.get_all("Journal", filters={"journal_type": BANK_JOURNAL_TYPE}, pluck="name")],
            ],
            limit=1,
        )
    )


# ── write endpoints ──────────────────────────────────────────────────────────


@frappe.whitelist()
def rapprocher(ecriture_names: str | list, date_rapprochement: str | None = None) -> dict:
    """Mark the selected ledger lines as reconciled (rapprochement_manuel = 1,
    date_rapprochement = the given or today's date). Touches the two
    reconciliation fields only; rows inside a clotured declaration stay
    reconcilable (the lock guards amounts, not clearing stamps)."""
    _check_write()
    context = _context()
    names = _parse_names(ecriture_names)
    rows = _fetch_rows(names, context)
    if not rows:
        frappe.throw(_("No ledger lines found for the selection."))
    if len(rows) < len(set(names)):
        frappe.throw(_("Certaines lignes n'appartiennent pas au contexte comptable."))
    _assert_bank_journal_rows(rows)

    cleared_on = getdate(date_rapprochement) if date_rapprochement else getdate(nowdate())
    validate_date_in_exercice(cleared_on, context, _("Date rapprochement"))

    for row in rows:
        frappe.db.set_value(
            LEDGER,
            row.name,
            {"date_rapprochement": cleared_on, "rapprochement_manuel": 1},
            update_modified=False,
        )
    return {"rapprochees": len(rows), "date_rapprochement": str(cleared_on)}


@frappe.whitelist()
def de_rapprocher(ecriture_names: str | list) -> dict:
    """Undo the reconciliation of the selected lines (both fields cleared)."""
    _check_write()
    context = _context()
    names = _parse_names(ecriture_names)
    rows = _fetch_rows(names, context)
    if not rows:
        frappe.throw(_("No ledger lines found for the selection."))
    if len(rows) < len(set(names)):
        frappe.throw(_("Certaines lignes n'appartiennent pas au contexte comptable."))
    _assert_bank_journal_rows(rows)

    for row in rows:
        frappe.db.set_value(
            LEDGER,
            row.name,
            {"date_rapprochement": None, "rapprochement_manuel": 0},
            update_modified=False,
        )
    return {"annulees": len(rows)}


@frappe.whitelist()
def set_solde_initial(account: str, solde_initial, mois: str, sens: str) -> dict:
    """Upsert the statement-side opening of one bank account for the
    context's Exercice (Solde Initial Banque — unique per Exercice +
    Compte). mois is the French month name the statement's Solde initial
    row refers to; sens reads the releve: Debit = solde crediteur banque
    (money available), Credit = solde debiteur."""
    _check_write()
    context = _context()
    account = (account or "").strip()
    if not account:
        frappe.throw(_("Compte de banque manquant."))
    if not _is_bank_account(account, context):
        frappe.throw(_("Le compte {0} n'est pas un compte de banque.").format(frappe.bold(account)))
    if mois not in MONTHS_FR:
        frappe.throw(_("Mois invalide: {0}.").format(frappe.bold(mois or "")))
    if sens not in ("Debit", "Credit"):
        frappe.throw(_("Sens invalide: {0} (Debit ou Credit).").format(frappe.bold(sens or "")))
    try:
        solde = round(float(solde_initial or 0), 3)
    except (TypeError, ValueError):
        frappe.throw(_("Solde initial invalide: {0}.").format(frappe.bold(str(solde_initial))))
    if solde < 0:
        frappe.throw(_("Le solde initial est un montant positif; le sens porte le signe."))

    existing = frappe.db.get_value(
        "Solde Initial Banque",
        {"entreprise": context["entreprise"], "exercice": context["exercice"], "account": account},
    )
    if existing:
        frappe.db.set_value(
            "Solde Initial Banque",
            existing,
            {"solde_initial": solde, "mois": mois, "sens": sens},
        )
        name = existing
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Solde Initial Banque",
                "entreprise": context["entreprise"],
                "exercice": context["exercice"],
                "account": account,
                "solde_initial": solde,
                "mois": mois,
                "sens": sens,
            }
        )
        doc.insert(ignore_permissions=True)
        name = doc.name
    return {"name": name, "solde_initial": solde, "mois": mois, "sens": sens}


# ── read endpoint (the page) ─────────────────────────────────────────────────


@frappe.whitelist()
def lignes(filters: str | dict | None = None) -> dict:
    """One page of the Rapprochement Manuel table: context-scoped, bank
    journals only, the period resolved against the Exercice
    (Mensuelle / Annuelle / Date a date — clamped, never outside), the rest
    of the filters applied by bank_statement_logic.filter_line_rows, footer
    totals + the filter dropdown options attached."""
    _check_write()  # the page is a write screen: same gate as its buttons
    context = require_context()
    filters = _parse_filters(filters)

    from erpnext.custom_modules.bank_reconciliation.bank_statement_logic import filter_line_rows, totals
    from erpnext.custom_modules.reports.report_common import resolve_period

    from_date, to_date = resolve_period(_period_filters(filters), context)

    ledger_filters = [
        ["entreprise", "=", context["entreprise"]],
        ["exercice", "=", context["exercice"]],
        ["journal", "in", frappe.get_all("Journal", filters={"journal_type": BANK_JOURNAL_TYPE}, pluck="name")],
    ]
    if filters.get("account"):
        ledger_filters.append(["account", "=", filters["account"]])
    if filters.get("journal"):
        ledger_filters.append(["journal", "=", filters["journal"]])
    if filters.get("tresorerie"):
        ledger_filters.append(["tresorerie", "=", filters["tresorerie"]])

    rows = frappe.get_all(
        LEDGER,
        filters=ledger_filters,
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
            "account",
            "tresorerie",
            "date_rapprochement",
            "rapprochement_manuel",
            "source_entry_doctype",
            "source_entry",
        ],
        order_by="posting_date asc, creation asc",
    )
    for row in rows:
        row["posting_date"] = getdate(row.posting_date) if row.posting_date else None
        row["date_rapprochement"] = getdate(row.date_rapprochement) if row.date_rapprochement else None

    rows = filter_line_rows(rows, {**filters, "from_date": from_date, "to_date": to_date})
    sums = totals(rows)
    return {"rows": rows, "totals": sums, "options": _filter_options()}


def _period_filters(filters: dict) -> dict:
    """The page's period selector maps onto resolve_period: 'Date a date' is
    its Personnalisee (whole Exercice when either bound is missing),
    Mensuelle carries the French month name, Annuelle spans the Exercice."""
    period_type = filters.get("period_type") or "Mensuelle"
    if period_type == "Date a date" and filters.get("from_date") and filters.get("to_date"):
        return {**filters, "period_type": "Personnalisee"}
    if period_type == "Annuelle":
        return {**filters, "period_type": "Annuelle"}
    return {**filters, "period_type": "Mensuelle"}


def _filter_options() -> dict:
    """The page's dropdowns: bank accounts, Banque journals, visible
    tresorerie pieces."""
    accounts = frappe.get_all(
        "Chart of Account",
        filters={"account_type": "Bank", "is_group": 0, "disabled": 0},
        fields=["name", "account_number", "account_name"],
        order_by="account_number asc",
    )
    return {
        "accounts": [
            {"value": row.name, "label": " ".join(x for x in (row.account_number, row.account_name) if x)}
            for row in accounts
        ],
        "journals": [
            {"value": row.name, "label": " ".join(x for x in (row.journal_code, row.journal_name) if x)}
            for row in frappe.get_all(
                "Journal",
                filters={"journal_type": BANK_JOURNAL_TYPE, "disabled": 0},
                fields=["name", "journal_code", "journal_name"],
                order_by="journal_code asc",
            )
        ],
        "tresoreries": [
            {"value": row.name, "label": row.libelle or row.name}
            for row in frappe.get_all(
                "Operation Tresorerie",
                filters={"visible": 1},
                fields=["name", "libelle"],
                order_by="ordre asc",
            )
        ],
    }


def _parse_filters(filters: str | dict | None) -> dict:
    if isinstance(filters, str):
        try:
            filters = json.loads(filters or "{}")
        except ValueError:
            filters = {}
    return filters or {}
