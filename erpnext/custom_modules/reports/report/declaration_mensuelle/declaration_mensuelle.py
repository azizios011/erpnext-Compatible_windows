# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Declaration Mensuelle — the Reports section's recap of the monthly
declarations over the dock context's Entreprise/Exercice.

One read-only whitelisted method (get_declaration_report_data) feeds the
three custom views (Tableau de bord, Fiche mois, Vue XLSX); the native script
report (execute) renders the RECAP grid itself, one row per calendar month
per the Source filter: Calculé (Declaration Transaction), Déclaré (Mensuelle
Ligne) or Écarts (declared minus calculated, out-of-tolerance cells
highlighted by the client). Entreprise and Exercice always come from the
dock context (organization.context), never from filters.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from erpnext.custom_modules.entries.declaration_engine import (
    DECLARATION_LINE_DOCTYPE,
    DM_DOCTYPE,
)
from erpnext.custom_modules.facturation.mensuelle_checks import ECART_TOLERANCE
from erpnext.custom_modules.organization.context import require_context
from erpnext.custom_modules.reports.declaration_recap_logic import (
    RECAP_COLUMNS,
    build_recap,
    dashboard_aggregates,
)
from erpnext.custom_modules.reports.report_common import check_ledger_read_permission

MENSUELLE_DOCTYPE = "Mensuelle"

# ── extraction: the doctypes as the pure recap reads them ────────────────────


def _declaration_figures(entreprise: str, exercice: str) -> dict[int, dict]:
    """The Principale Declaration Transaction of each month as the recap's
    Calculé payload (lines + totals + the portal receipt)."""
    rows: dict[int, dict] = {}
    declarations = frappe.get_all(
        DM_DOCTYPE,
        filters={
            "entreprise": entreprise,
            "exercice": exercice,
            "type_declaration": "Principale",
        },
        fields=[
            "name",
            "mois",
            "status",
            "tva_collectee",
            "tva_deductible",
            "tva_a_payer",
            "credit_suivant",
            "total_rs",
            "total_tfp",
            "total_foprolos",
            "total_timbre",
            "total_tcl",
            "total_a_payer",
            "numero_declaration",
            "montant_liquide",
        ],
        order_by="mois asc",
    )
    if not declarations:
        return rows

    lines = frappe.get_all(
        DECLARATION_LINE_DOCTYPE,
        filters={
            "parenttype": DM_DOCTYPE,
            "parent": ("in", [row.name for row in declarations]),
        },
        fields=["parent", "code", "libelle", "montant_brut", "retenu"],
        order_by="idx asc",
    )
    lines_by_parent: dict[str, list[dict]] = {}
    for line in lines:
        lines_by_parent.setdefault(line.parent, []).append(
            {
                "code": line.code,
                "libelle": line.libelle,
                "montant_brut": float(line.montant_brut or 0),
                "retenu": float(line.retenu or 0),
            }
        )

    portail_lines = frappe.get_all(
        "Declaration Transaction Portail Ligne",
        filters={
            "parenttype": DM_DOCTYPE,
            "parent": ("in", [row.name for row in declarations]),
        },
        fields=["parent", "impot", "montant_principal", "deduction", "taxe_due_ou_report", "penalites_retard", "total"],
        order_by="idx asc",
    )
    portail_by_parent: dict[str, list[dict]] = {}
    for line in portail_lines:
        portail_by_parent.setdefault(line.parent, []).append(
            {
                "impot": line.impot,
                "montant_principal": float(line.montant_principal or 0),
                "deduction": float(line.deduction or 0),
                "taxe_due_ou_report": float(line.taxe_due_ou_report or 0),
                "penalites_retard": float(line.penalites_retard or 0),
                "total": float(line.total or 0),
            }
        )

    for row in declarations:
        month = cint(row.mois)
        if not 1 <= month <= 12:
            continue
        portal_lines = portail_by_parent.get(row.name, [])
        rows[month] = {
            "name": row.name,
            "status": row.status,
            "lines": lines_by_parent.get(row.name, []),
            "tva_collectee": float(row.tva_collectee or 0),
            "tva_deductible": float(row.tva_deductible or 0),
            "tva_a_payer": float(row.tva_a_payer or 0),
            "credit_suivant": float(row.credit_suivant or 0),
            "total_a_payer": float(row.total_a_payer or 0),
            "numero_declaration": row.numero_declaration or "",
            "portal": {"lines": portal_lines, "montant_liquide": float(row.montant_liquide or 0)} if portal_lines else None,
        }
    return rows


def _mensuelle_figures(entreprise: str, exercice: str) -> dict[int, dict]:
    """The Mensuelle of each month as the recap's Déclaré payload (lignes +
    the document metadata for the Fiche mois / Vue XLSX)."""
    rows: dict[int, dict] = {}
    mensuelles = frappe.get_all(
        MENSUELLE_DOCTYPE,
        filters={"entreprise": entreprise, "exercice": exercice},
        fields=[
            "name",
            "period_month",
            "check_status",
            "declared_total",
            "source_file",
            "source_sheet",
            "sheet_file",
        ],
        order_by="period_month asc, creation desc",
    )
    if not mensuelles:
        return rows

    lignes = frappe.get_all(
        "Mensuelle Ligne",
        filters={
            "parenttype": MENSUELLE_DOCTYPE,
            "parent": ("in", [row.name for row in mensuelles]),
        },
        fields=["parent", "code_rubrique", "base_declaree", "montant_declare"],
        order_by="idx asc",
    )
    controles = frappe.get_all(
        "Mensuelle Controle",
        filters={
            "parenttype": MENSUELLE_DOCTYPE,
            "parent": ("in", [row.name for row in mensuelles]),
        },
        fields=["parent", "check_code", "severity", "message", "declare", "attendu", "ecart"],
        order_by="idx asc",
    )

    def latest_file_docname(sheet_file: str) -> str:
        if not sheet_file:
            return ""
        return frappe.db.get_value("File", {"file_url": sheet_file}, "name") or ""

    lignes_by_parent: dict[str, list[dict]] = {}
    for line in lignes:
        lignes_by_parent.setdefault(line.parent, []).append(
            {
                "code_rubrique": line.code_rubrique,
                "base_declaree": float(line.base_declaree) if line.base_declaree is not None else None,
                "montant_declare": float(line.montant_declare) if line.montant_declare is not None else None,
            }
        )
    controles_by_parent: dict[str, list[dict]] = {}
    for control in controles:
        controles_by_parent.setdefault(control.parent, []).append(
            {
                "check_code": control.check_code,
                "severity": control.severity,
                "message": control.message,
                "declare": float(control.declare) if control.declare is not None else None,
                "attendu": float(control.attendu) if control.attendu is not None else None,
                "ecart": float(control.ecart) if control.ecart is not None else None,
            }
        )

    seen: set[int] = set()
    for row in mensuelles:
        month = cint(row.period_month)
        if not 1 <= month <= 12 or month in seen:
            continue
        seen.add(month)
        rows[month] = {
            "name": row.name,
            "check_status": row.check_status or "Non verifie",
            "declared_total": float(row.declared_total or 0),
            "source_file": row.source_file or "",
            "source_sheet": row.source_sheet or "",
            "sheet_file": row.sheet_file or "",
            "sheet_file_docname": latest_file_docname(row.sheet_file),
            "lignes": lignes_by_parent.get(row.name, []),
            "controles": controles_by_parent.get(row.name, []),
        }
    return rows


def build_report_data(context: dict) -> dict:
    """Everything the views need for one context: the three recap views, the
    dashboard aggregates and the per-month details."""
    entreprise, exercice = context["entreprise"], context["exercice"]
    calcule = _declaration_figures(entreprise, exercice)
    declare = _mensuelle_figures(entreprise, exercice)
    liquide = {
        month: {"lines": payload.get("portal", {}).get("lines") or [], "montant_liquide": payload.get("portal", {}).get("montant_liquide")}
        for month, payload in calcule.items()
        if payload.get("portal")
    }
    recap = build_recap(
        calcule,
        {month: payload["lignes"] for month, payload in declare.items()},
        liquide,
        tolerance=ECART_TOLERANCE,
    )
    dm_status = {
        month: (calcule[month].get("status") if month in calcule else None)
        for month in range(1, 13)
    }
    return {
        "entreprise": entreprise,
        "entreprise_label": context.get("entreprise_label") or entreprise,
        "exercice": exercice,
        "exercice_label": context.get("exercice_label") or exercice,
        "recap": recap,
        "dashboard": dashboard_aggregates(recap, dm_status),
        "details": {
            "calcule": calcule,
            "declare": declare,
        },
        "portal": {
            month: {
                "numero_declaration": payload.get("numero_declaration", ""),
                "montant_liquide": payload.get("portal", {}).get("montant_liquide")
                if payload.get("portal")
                else None,
            }
            for month, payload in calcule.items()
        },
    }


def get_declaration_report_data() -> dict:
    """All views' data for the current dock context (read-only)."""
    context = require_context()
    check_ledger_read_permission()
    return build_report_data(context)


# ── the native RECAP table (script report) ───────────────────────────────────


def _recap_columns() -> list[dict]:
    columns = []
    for key, label in RECAP_COLUMNS:
        if key == "mois":
            columns.append({"label": _(label), "fieldname": "mois", "fieldtype": "Data", "width": 70})
        else:
            columns.append(
                {"label": _(label), "fieldname": key, "fieldtype": "Currency", "precision": "3", "width": 110}
            )
    return columns


SOURCE_KEYS = {
    "Calcule": "calcule",
    "Calculé": "calcule",
    "Declare": "declare",
    "Déclaré": "declare",
    "Liquide": "liquide",
    "Liquidé": "liquide",
    "Ecarts": "ecarts",
    "Écarts": "ecarts",
}


def execute(filters=None) -> tuple:
    """The RECAP grid as the native script-report table (the default view):
    the 12 month rows per the Source filter + the totals row (for Écarts, one
    totals row per comparison pair). Entreprise and Exercice come from the
    dock context only."""
    filters = filters or {}
    context = require_context()
    check_ledger_read_permission()
    source_key = SOURCE_KEYS.get(filters.get("source") or "Calcule", "calcule")

    data = build_report_data(context)
    recap = data["recap"]
    if source_key == "ecarts":
        rows = list(recap["rows"]["ecarts"])
        for totals in (recap["totals"]["ecarts"] or {}).values():
            rows.append(dict(totals))
    else:
        rows = list(recap["rows"][source_key])
        totals = dict(recap["totals"][source_key])
        totals["mois"] = _("TOTAL")
        rows.append(totals)
    return _recap_columns(), rows, None, None, None
