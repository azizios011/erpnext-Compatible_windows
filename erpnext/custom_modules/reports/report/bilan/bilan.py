# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Bilan — the Tunisian SCE balance sheet over the Ecriture Comptable
ledger, for the dock context's Entreprise and Exercice.

One row per rubrique of the sce_mapping tree, with Exercice N (the context
Exercice, balances up to the resolved period end), Exercice N-1 (the same
Entreprise's Exercice of the previous year, full range — a blank column when
that Exercice does not exist), Variation and Variation %. Section rows and
the two grand totals (Total Actifs vs Total Capitaux Propres + Passifs) ride
the same table; the summary card and the message banner carry the equilibre
verdict. Clicking a rubrique opens Ledger Data prefiltered to its account
prefixes (the client wires the route from the row's saisie_libre tokens).
Accounts with balances matching no rubrique are listed in the message as
unmapped — never guessed into a line.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import (
    BALANCE_TOLERANCE,
    REPORT_CURRENCY,
    check_ledger_read_permission,
    exercice_year,
    resolve_period,
)
from erpnext.custom_modules.reports.sce_mapping import (
    BILAN_RUBRIQUES,
    build_bilan,
)

LEDGER_DOCTYPE = "Ecriture Comptable"


def execute(filters=None) -> tuple:
    filters = filters or {}
    context = require_context()
    check_ledger_read_permission()

    from_date, to_date = resolve_period(filters, context)
    annee = exercice_year(context)

    balances_n = _balances(context["entreprise"], context["exercice"], up_to=to_date)
    previous = frappe.db.get_value(
        "Exercice",
        {"entreprise": context["entreprise"], "annee": annee - 1},
        ["name", "date_debut", "date_fin"],
        as_dict=True,
    )
    balances_n1 = _balances(context["entreprise"], previous.name) if previous else None

    bilan = build_bilan(balances_n, balances_n1, tolerance=BALANCE_TOLERANCE)
    rows = _report_rows(bilan, annee, annee - 1 if previous else None)

    summary = _summary(bilan)
    message = _message(bilan, annee, previous)
    return _columns(), rows, message, None, summary


def _balances(entreprise: str, exercice: str, up_to=None) -> dict[str, dict] | None:
    """{account_number: {debit, credit}} over one Exercice's ledger rows
    (cumulative up to `up_to` when given, otherwise the whole Exercice)."""
    ledger_filters = [
        ["entreprise", "=", entreprise],
        ["exercice", "=", exercice],
    ]
    if up_to:
        ledger_filters.append(["posting_date", "<=", up_to])
    rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters=ledger_filters,
        fields=["account", "debit", "credit"],
    )
    numbers = frappe.get_all(
        "Chart of Account",
        filters={"entreprise": entreprise, "name": ("in", {row.account for row in rows})} if rows else {"name": ""},
        fields=["name", "account_number"],
    )
    number_of = {n.name: (n.account_number or "").strip() for n in numbers}

    balances: dict[str, dict] = {}
    for row in rows:
        number = number_of.get(row.account, "")
        if not number:
            continue
        entry = balances.setdefault(number, {"debit": 0.0, "credit": 0.0})
        entry["debit"] = flt(entry["debit"] + flt(row.debit), 3)
        entry["credit"] = flt(entry["credit"] + flt(row.credit), 3)
    return balances or None


def _report_rows(bilan: dict, annee: int, annee_1: int | None) -> list[dict]:
    """The flat report rows: sections, rubriques (with the drill-down tokens)
    and the totals, plus the two grand-total rows."""
    out: list[dict] = []
    prefix_by_key = {r["key"]: r for r in BILAN_RUBRIQUES}
    for row in bilan["rows"]:
        out_row = {
            "row_type": row["row_type"],
            "rubrique": row["rubrique"],
            "exercice_n": row.get("exercice_n"),
            "exercice_n1": row.get("exercice_n1"),
            "variation": row.get("variation"),
            "variation_pct": row.get("variation_pct"),
            "annee_n": annee,
            "annee_n1": annee_1,
        }
        if row["row_type"] == "rubrique":
            rubrique = prefix_by_key.get(row["key"])
            if rubrique:
                tokens = list(rubrique.get("prefixes") or []) + list(rubrique.get("nets") or [])
                out_row["saisie_libre"] = ", ".join(tokens)
        out.append(out_row)

    out.append(
        {
            "row_type": "grand_total",
            "rubrique": _("TOTAL ACTIFS"),
            "exercice_n": bilan["totals"]["exercice_n"]["actif"],
            "exercice_n1": bilan["totals"]["exercice_n1"]["actif"],
            "variation": round(bilan["totals"]["exercice_n"]["actif"] - bilan["totals"]["exercice_n1"]["actif"], 3),
        }
    )
    out.append(
        {
            "row_type": "grand_total",
            "rubrique": _("TOTAL CAPITAUX PROPRES + PASSIFS"),
            "exercice_n": bilan["totals"]["exercice_n"]["passif"],
            "exercice_n1": bilan["totals"]["exercice_n1"]["passif"],
            "variation": round(bilan["totals"]["exercice_n"]["passif"] - bilan["totals"]["exercice_n1"]["passif"], 3),
        }
    )
    return out


def _columns() -> list[dict]:
    return [
        {"label": _("Rubrique"), "fieldname": "rubrique", "fieldtype": "Data", "width": 340},
        {"label": _("Exercice {0}").format("N"), "fieldname": "exercice_n", "fieldtype": "Currency", "precision": "3", "width": 150},
        {"label": _("Exercice N-1"), "fieldname": "exercice_n1", "fieldtype": "Currency", "precision": "3", "width": 150},
        {"label": _("Variation"), "fieldname": "variation", "fieldtype": "Currency", "precision": "3", "width": 130},
        {"label": _("Variation %"), "fieldname": "variation_pct", "fieldtype": "Percent", "precision": "2", "width": 100},
        {"label": _("Exercice N"), "fieldname": "annee_n", "fieldtype": "Int", "hidden": 1},
        {"label": _("Exercice N-1"), "fieldname": "annee_n1", "fieldtype": "Int", "hidden": 1},
        {"label": _("Saisie libre"), "fieldname": "saisie_libre", "fieldtype": "Data", "hidden": 1},
    ]


def _summary(bilan: dict) -> list[dict]:
    equilibre = bilan["equilibre"]
    return [
        {"label": _("Total Actifs"), "value": bilan["totals"]["exercice_n"]["actif"], "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Blue"},
        {"label": _("Total Capitaux Propres + Passifs"), "value": bilan["totals"]["exercice_n"]["passif"], "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Blue"},
        {
            "label": _("Equilibre") if equilibre else _("Non equilibre"),
            "value": bilan["difference"],
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Green" if equilibre else "Red",
        },
    ]


def _message(bilan: dict, annee: int, previous) -> str | None:
    parts = []
    if bilan["equilibre"]:
        parts.append(_("Bilan equilibre: Total Actifs ({0}) = Total Capitaux Propres + Passifs ({1}).").format(
            frappe.utils.fmt_money(bilan["totals"]["exercice_n"]["actif"], currency=REPORT_CURRENCY),
            frappe.utils.fmt_money(bilan["totals"]["exercice_n"]["passif"], currency=REPORT_CURRENCY),
        ))
    else:
        parts.append(
            _("Bilan NON equilibre: Total Actifs ({0}) vs Capitaux Propres + Passifs ({1}) — difference {2}. "
              "Verifiez les comptes non mappes ci-dessous et les ecritures de l'exercice.").format(
                frappe.utils.fmt_money(bilan["totals"]["exercice_n"]["actif"], currency=REPORT_CURRENCY),
                frappe.utils.fmt_money(bilan["totals"]["exercice_n"]["passif"], currency=REPORT_CURRENCY),
                frappe.utils.fmt_money(bilan["difference"], currency=REPORT_CURRENCY),
            )
        )
    if not previous:
        parts.append(_("Aucun Exercice {0} pour cette Entreprise: la colonne N-1 est vide.").format(annee - 1))
    unmapped = (bilan["unmapped"] or {}).get("n") or []
    if unmapped:
        detail = ", ".join(f"{row['number']} ({row['net']})" for row in unmapped[:12])
        more = _(" … et {0} autres").format(len(unmapped) - 12) if len(unmapped) > 12 else ""
        parts.append(
            _("Comptes non classes dans le Bilan (prefixes absents du mapping SCE): {0}{1}.").format(detail, more)
        )
    return " ".join(parts)
