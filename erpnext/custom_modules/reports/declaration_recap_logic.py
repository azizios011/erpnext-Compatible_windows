# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free assembly of the Déclaration Mensuelle recap grid (the
employee's "RECAP 2026" sheet) over one Entreprise/Exercice year.

One row per calendar month, January-December, three parallel views:

- **calcule** — from the Declaration Transaction of the month (the ledger
  computation; the adapter feeds the rubrique figures + the DM totals);
- **declare** — from the Mensuelle Ligne rows (what the imported workbook
  declared; CNSS derives as S.BRUT - S.IMPOS, the TVA position derives from
  the declared collected/deductible because the workbook's carry is not
  captured per ligne);
- **ecarts** — declared minus calculated per column, blank when either side
  is missing; cells beyond ECART_TOLERANCE are flagged for highlighting.

Months with nothing yet are blank rows, never zeros. A totals row sums every
column over the present months. Everything here is unit-testable without a
site; the frappe adapter lives in the report module.
"""

from __future__ import annotations

# The recap matrix, in Axeane's column order: (field key, French label).
RECAP_COLUMNS: list[tuple[str, str]] = [
    ("mois", "MOIS"),
    ("ht7", "HT7"),
    ("tva7", "TVA7"),
    ("ht19", "HT19"),
    ("tva19", "TVA19"),
    ("vt_susp", "VT en susp"),
    ("ttc", "TTC"),
    ("tcl", "TCL"),
    ("ded_base", "AC"),
    ("tva_deductible", "TVA AC"),
    ("timbre", "DT"),
    ("tva_a_payer", "P"),
    ("credit_suivant", "R"),
    ("gross", "S.BRUT"),
    ("cnss", "CNSS"),
    ("s_impos", "S.IMPOS"),
    ("irpp", "IRPP"),
    ("css", "CSS"),
    ("tfp", "TFP"),
    ("foprolos", "FOPROLOS"),
    ("rs1", "RS 1%"),
    ("rs3", "RS 3%"),
    ("loyer", "Loyer"),
    ("rs_loyer", "RS Loyer"),
    ("total", "TOTAL"),
]

RECAP_KEYS = [key for key, _label in RECAP_COLUMNS if key != "mois"]
NUMERIC_KEYS = RECAP_KEYS

# Out-of-tolerance écart cells get highlighted in the Écarts view.
ECART_TOLERANCE = 0.005

# rubrique code -> (the calculated DM figure, the declared Mensuelle figure)
# on the recap grid. (dm_key, declared_key) — None = not captured on a side.
RUBRIQUE_RECAP_MAP: dict[str, dict] = {
    "F5_1_1": {"calcule": ("ht7", "tva7"), "declare": ("ht7", "tva7")},
    "F5_1_3": {"calcule": ("ht19", "tva19"), "declare": ("ht19", "tva19")},
    "F9_3_1": {"calcule": (None, "tcl"), "declare": (None, "tcl")},
    "F5_2_4": {"calcule": (None, "tva_deductible"), "declare": ("ded_base", "tva_deductible")},
    "F7": {"calcule": (None, "timbre"), "declare": (None, "timbre")},
    "F1_1": {"calcule": ("gross", "irpp"), "declare": ("gross", "irpp")},
    "F1_3": {"calcule": (None, "css"), "declare": (None, "css")},
    "F2_1": {"calcule": (None, "tfp"), "declare": (None, "tfp")},
    "F3_1": {"calcule": (None, "foprolos"), "declare": (None, "foprolos")},
    "F1_17_1": {"calcule": (None, "rs1"), "declare": (None, "rs1")},
    "F1_6": {"calcule": (None, "rs3"), "declare": (None, "rs3")},
    "F1_4_1": {"calcule": ("loyer", "rs_loyer"), "declare": ("loyer", "rs_loyer")},
}


def blank_month_row(month: int) -> dict:
    """A month with nothing yet: every figure blank, never zero."""
    row = {"mois": f"{month:02d}"}
    for key in NUMERIC_KEYS:
        row[key] = None
    return row


def row_from_declaration(month: int, dm: dict | None) -> dict:
    """The Calculé row from one month's Declaration Transaction payload:
    {lines: [{code, montant_brut, retuni? no — retenu}], totals by key}."""
    row = blank_month_row(month)
    if not dm:
        return row
    lines = {line["code"]: line for line in (dm.get("lines") or [])}
    for code, mapping in RUBRIQUE_RECAP_MAP.items():
        line = lines.get(code)
        if not line:
            continue
        brut_key, retenu_key = mapping["calcule"]
        if brut_key:
            row[brut_key] = line.get("montant_brut")
        if retenu_key:
            row[retenu_key] = line.get("retenu")
    row["tva_a_payer"] = dm.get("tva_a_payer")
    row["credit_suivant"] = dm.get("credit_suivant")
    row["total"] = dm.get("total_a_payer")
    return row


def row_from_mensuelle(month: int, lignes: list[dict] | None) -> dict:
    """The Déclaré row from one month's Mensuelle Ligne rows
    ({code_rubrique, base_declaree, montant_declare}). The TVA position and
    the CNSS derive: the workbook's carry is not captured per ligne."""
    row = blank_month_row(month)
    if not lignes:
        return row
    lines = {line.get("code_rubrique"): line for line in lignes}
    for code, mapping in RUBRIQUE_RECAP_MAP.items():
        line = lines.get(code)
        if not line:
            continue
        base_key, montant_key = mapping["declare"]
        if base_key:
            row[base_key] = line.get("base_declaree")
        if montant_key:
            row[montant_key] = line.get("montant_declare")

    if "S_IMPOS" in lines:
        row["s_impos"] = lines["S_IMPOS"].get("base_declaree")
    # CNSS = the social-security share between the gross and the taxable pay
    if row["gross"] is not None and row["s_impos"] is not None:
        row["cnss"] = round(row["gross"] - row["s_impos"], 3)

    # the declared TVA position from the declared collected/deductible (the
    # workbook's carry is not part of the captured lignes): a positive
    # position is the P column, a negative one the R credit
    collected = sum(
        value
        for value in (
            row.get("tva7"),
            row.get("tva19"),
            (lines.get("F5_1_2") or {}).get("montant_declare"),
            (lines.get("F5_3_1") or {}).get("montant_declare"),
        )
        if value is not None
    )
    deductible = sum(
        value
        for code, line in lines.items()
        if code.startswith("F5_2_") and line.get("montant_declare") is not None
        for value in [line["montant_declare"]]
    )
    if collected or deductible:
        position = round(collected - deductible, 3)
        if position > 0:
            row["tva_a_payer"] = position
        else:
            row["credit_suivant"] = -position

    if "TOTAL" in lines:
        row["total"] = lines["TOTAL"].get("montant_declare")
    return row


def ecart_row(month: int, calcule_row: dict, declare_row: dict, tolerance: float = ECART_TOLERANCE) -> dict:
    """The Écarts row: declared - calculated per column where BOTH sides
    carry a figure; `out_of_tolerance` names the columns to highlight."""
    row = blank_month_row(month)
    out: list[str] = []
    for key in NUMERIC_KEYS:
        declared, calculated = declare_row.get(key), calcule_row.get(key)
        if declared is None or calculated is None:
            continue
        ecart = round(float(declared) - float(calculated), 3)
        row[key] = ecart
        if abs(ecart) > tolerance:
            out.append(key)
    row["out_of_tolerance"] = out
    return row


def totals_row(rows: list[dict]) -> dict:
    """The bottom totals row: each column sums over the months that carry a
    figure (blank columns stay blank)."""
    totals = {"mois": "TOTAL"}
    for key in NUMERIC_KEYS:
        values = [row.get(key) for row in rows if row.get(key) is not None]
        totals[key] = round(sum(float(v) for v in values), 3) if values else None
    return totals


def build_recap(
    calcule_rows: dict[int, dict],
    declare_rows: dict[int, dict],
    tolerance: float = ECART_TOLERANCE,
) -> dict:
    """The whole grid: 12 month rows per source + the écart view + the totals
    row + the months whose écarts go beyond the tolerance.

    calcule_rows / declare_rows: {month: figures} as the frappe adapter
    extracts them (missing months stay blank)."""
    calcule = {month: row_from_declaration(month, calcule_rows.get(month)) for month in range(1, 13)}
    declare = {month: row_from_mensuelle(month, declare_rows.get(month)) for month in range(1, 13)}
    ecarts = {
        month: ecart_row(month, calcule[month], declare[month], tolerance) for month in range(1, 13)
    }
    months_with_ecarts = [
        month for month in range(1, 13) if ecarts[month]["out_of_tolerance"]
    ]
    return {
        "months": list(range(1, 13)),
        "columns": [{"key": key, "label": label} for key, label in RECAP_COLUMNS],
        "ecart_tolerance": tolerance,
        "rows": {
            "calcule": [calcule[month] for month in range(1, 13)],
            "declare": [declare[month] for month in range(1, 13)],
            "ecarts": [ecarts[month] for month in range(1, 13)],
        },
        "totals": {
            "calcule": totals_row(list(calcule.values())),
            "declare": totals_row(list(declare.values())),
            "ecarts": totals_row(list(ecarts.values())),
        },
        "ecart_months": months_with_ecarts,
    }


def dashboard_aggregates(recap: dict, dm_status: dict[int, str | None]) -> dict:
    """The TABLEAU DE BORD numbers, from the same recap: the cumuls come from
    the Calculé source, the month counters from the DM statuses and the écart
    months."""
    calcule_totals = recap["totals"]["calcule"]
    declare_totals = recap["totals"]["declare"]
    deposited = sum(1 for status in dm_status.values() if status == "Depose")
    cloture = sum(1 for status in dm_status.values() if status == "Cloture")
    return {
        "total_a_payer_cumule": calcule_totals.get("total") or 0.0,
        "total_a_payer_cumule_declare": declare_totals.get("total") or 0.0,
        "tva_nette_cumulee": round(
            (calcule_totals.get("tva_a_payer") or 0.0) - (calcule_totals.get("credit_suivant") or 0.0), 3
        ),
        # all retenus a la source: IRPP + CSS + RS 1% + RS 3% + RS loyers
        "rs_cumules": round(
            sum(calcule_totals.get(key) or 0.0 for key in ("irpp", "css", "rs1", "rs3", "rs_loyer")), 3
        ),
        "months_depose": deposited,
        "months_cloture": cloture,
        "months_a_faire": 12 - deposited - cloture,
        "months_with_ecarts": recap["ecart_months"],
        "months_with_ecarts_count": len(recap["ecart_months"]),
    }
