# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Etat de Resultat — the Tunisian SCE income cascade over the Ecriture
Comptable ledger, for the dock context's Entreprise and Exercice.

Same N / N-1 / Variation / Variation % layout as the Bilan: Exercice N
carries the balances up to the resolved period end, N-1 the previous
Exercice's full range (blank column when none). The cascade computes the
resultat d'exploitation, the resultat ordinaire apres impot and the
resultat net; the summary card reads Benefice net / Perte nette. Clicking a
rubrique opens Ledger Data prefiltered to its account prefixes.
"""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.report_common import (
    REPORT_CURRENCY,
    check_ledger_read_permission,
    exercice_year,
    resolve_period,
)
from erpnext.custom_modules.reports.report.bilan.bilan import _balances
from erpnext.custom_modules.reports.sce_mapping import build_etat

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

    etat = build_etat(balances_n, balances_n1)
    rows = _report_rows(etat, annee, annee - 1 if previous else None)

    summary = _summary(etat)
    message = _message(etat, annee, previous)
    return _columns(), rows, message, None, summary


def _report_rows(etat: dict, annee: int, annee_1: int | None) -> list[dict]:
    out: list[dict] = []
    for row in etat["rows"]:
        out.append(
            {
                "row_type": row["row_type"],
                "rubrique": row["rubrique"],
                "exercice_n": row.get("exercice_n"),
                "exercice_n1": row.get("exercice_n1"),
                "variation": row.get("variation"),
                "variation_pct": row.get("variation_pct"),
                "annee_n": annee,
                "annee_n1": annee_1,
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


def _summary(etat: dict) -> list[dict]:
    net = etat["resultat_net"]
    benefice = etat["benefice"]
    return [
        {
            "label": _("Benefice net") if benefice else _("Perte nette"),
            "value": net,
            "datatype": "Currency",
            "currency": REPORT_CURRENCY,
            "precision": 3,
            "indicator": "Green" if benefice else "Red",
        },
        {"label": _("Produits d'exploitation"), "value": etat.get("produits_n"), "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Blue"},
        {"label": _("Charges d'exploitation"), "value": etat.get("charges_n"), "datatype": "Currency", "currency": REPORT_CURRENCY, "precision": 3, "indicator": "Orange"},
    ]


def _message(etat: dict, annee: int, previous) -> str | None:
    net = etat["resultat_net"]
    parts = [
        _("Resultat net {0}: {1}.").format(
            _("Benefice") if etat["benefice"] else _("Perte"),
            frappe.utils.fmt_money(net, currency=REPORT_CURRENCY),
        )
    ]
    if not previous:
        parts.append(_("Aucun Exercice {0} pour cette Entreprise: la colonne N-1 est vide.").format(annee - 1))
    unmapped = (etat["unmapped"] or {}).get("n") or []
    if unmapped:
        detail = ", ".join(f"{row['number']} ({row['net']})" for row in unmapped[:12])
        more = _(" … et {0} autres").format(len(unmapped) - 12) if len(unmapped) > 12 else ""
        parts.append(
            _("Comptes non classes dans l'Etat de Resultat (prefixes absents du mapping SCE): {0}{1}.").format(detail, more)
        )
    return " ".join(parts)
