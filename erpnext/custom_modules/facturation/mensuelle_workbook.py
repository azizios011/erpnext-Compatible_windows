# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Déclaration Mensuelle workbook reader (openpyxl adapter).

The CPR workbook carries one sheet per monthly declaration ("DM 01".."dm 10",
case and trailing spaces vary), a "RECAP 2026" month-per-row summary and
scratch sheets ("Feuil1", "Feuille 2") that are ignored. Two layout profiles
exist, derived from the real workbook by label anchors:

- **legacy** (DM 01-06): the header digits sit on row 4 (year at B4:E4 with
  the "السنة" anchor at F4, month at I4:J4), the RS block at A17..A24, TFP /
  FOPROLOS at C27 / C31, the TVA block at G33 / G35 / B39, the timbre at B55
  and the TCL at A57; the grand total sums P62..P75.
- **recent** (DM 07-10): the header digits moved to row 5 (A5 carries the
  string "2 0"), the RS block at A17 / A18 / A20 / A22 / A23, TFP /
  FOPROLOS at C28 / B31, the TVA block at E34 / E36 / A41, the timbre at
  B69 and the TCL at A72; the grand total sums P78..P87 and gains its TVA
  line from DM 08 onward.

Every workbook is read TWICE (formulas and data_only values): a formula cell
without a cached value is an import error telling the user to open and
re-save the file in Excel.
"""

from __future__ import annotations

import re

SHEET_NAME_PATTERN = re.compile(r"(?i)^dm\s*(\d{1,2})$")
IGNORED_SHEET_MARKERS = ("feuil1", "feuille")
RECAP_SHEET_NAME = "recap"

LAYOUT_LEGACY = "legacy"
LAYOUT_RECENT = "recent"

# Arabic anchors used to detect the layout profile.
ANCHOR_YEAR = "السنة"

# figure key -> (legacy cell, recent cell); None = the profile has no such
# figure. Every figure may be a typed value or a formula (its cached value is
# what the checks read; the formula travels for the audit trail).
FIGURE_CELLS: dict[str, tuple[str | None, str | None]] = {
    "year_digit_1": ("B4", "A5"),
    "year_digit_2": ("C4", "B5"),
    "year_digit_3": ("D4", "C5"),
    "year_digit_4": ("E4", None),  # the recent profile packs '2 0' into A5
    "month_digit_1": ("I4", "G5"),
    "month_digit_2": ("J4", "H5"),
    "tax_id_digit_1": ("J8", "H8"),
    "tax_id_digit_2": ("K8", "I8"),
    "tax_id_digit_3": ("L8", "J8"),
    "tax_id_digit_4": ("M8", "K8"),
    "tax_id_digit_5": ("N8", "L8"),
    "tax_id_digit_6": ("O8", "M8"),
    "tax_id_digit_7": ("P8", "N8"),
    "tax_id_letter": ("Q8", "O8"),
    "irpp": ("A17", "A17"),
    "s_impos": ("L17", "J17"),
    "css": ("A18", "A18"),
    "rs_loyer": ("A19", "A20"),
    "rs_loyer_rate": ("J19", "H20"),
    "rs_loyer_base": ("L19", "J20"),
    "rs3": ("A21", "A22"),
    "rs3_rate": ("J21", "H22"),
    "rs3_base": ("L21", "J22"),
    "rs1": ("A23", "A23"),
    "rs1_rate": ("J23", "H23"),
    "rs1_base": ("L23", "J23"),
    "rs_total": ("A24", "A24"),
    "tfp": ("C27", "C28"),
    "tfp_rate": ("J27", "H28"),
    "gross": ("M27", "J28"),
    "foprolos": ("C31", "B31"),
    "foprolos_rate": ("J31", "H31"),
    "ht7": ("P33", "L34"),
    "tva7": ("G33", "E34"),
    "tva7_rate": ("M33", "I34"),
    "ht19": ("P35", "L36"),
    "tva19": ("G35", "E36"),
    "tva19_rate": ("N35", "I36"),
    "ded_equip": ("B37", "A38"),
    "ded_autres": ("B39", "A41"),
    "ded_base": ("P39", "L41"),
    "tva_collectee": ("G43", "E48"),
    "tva_deductible": ("B43", "A48"),
    "carry_prev": ("D45", "G50"),
    "tva_due": ("D46", "G51"),
    "timbre": ("B55", "B69"),
    "timbre_count": ("N55", "I68"),
    "tcl": ("A57", "A72"),
    "tcl_rate": ("G57", "E72"),
    "ttc": ("J57", "H72"),
    "total": ("P76", "P88"),
}

# The declared figures mapped to the Axeane rubrique codes. (base, montant)
# name the FIGURE_CELLS keys; base None = the rubrique declares no base.
RUBRIQUE_MAP: list[dict] = [
    {"code": "F1_1", "libelle": "RS Salaires (IRPP)", "base": "gross", "montant": "irpp"},
    {"code": "F1_3", "libelle": "CSS", "base": None, "montant": "css"},
    {"code": "F1_4_1", "libelle": "RS Loyers (10%)", "base": "rs_loyer_base", "montant": "rs_loyer"},
    {"code": "F1_6", "libelle": "RS Honoraires (3%)", "base": "rs3_base", "montant": "rs3"},
    {"code": "F1_17_1", "libelle": "RS Fournisseurs (1%)", "base": "rs1_base", "montant": "rs1"},
    {"code": "F2_1", "libelle": "TFP", "base": "gross", "montant": "tfp"},
    {"code": "F3_1", "libelle": "FOPROLOS", "base": "gross", "montant": "foprolos"},
    {"code": "F5_1_1", "libelle": "CA soumis a TVA 7%", "base": "ht7", "montant": "tva7"},
    {"code": "F5_1_3", "libelle": "CA soumis a TVA 19%", "base": "ht19", "montant": "tva19"},
    {"code": "F5_2_4", "libelle": "TVA deductible autres achats locaux", "base": "ded_base", "montant": "ded_autres"},
    {"code": "F7", "libelle": "Droit de timbre", "base": "timbre_count", "montant": "timbre"},
    {"code": "F9_3_1", "libelle": "TCL chiffre d'affaires brut local", "base": "ttc", "montant": "tcl"},
    {"code": "TOTAL", "libelle": "Grand total declare", "base": None, "montant": "total"},
]


def parse_sheet_month(sheet_name: str) -> int | None:
    """'DM 01' / 'dm 9' / 'DM 06 ' -> the sheet's month number, else None."""
    match = SHEET_NAME_PATTERN.match((sheet_name or "").strip())
    return int(match.group(1)) if match else None


def is_monthly_sheet(sheet_name: str) -> bool:
    lowered = (sheet_name or "").strip().lower()
    return lowered.startswith("dm") and parse_sheet_month(sheet_name) is not None


def is_ignored_sheet(sheet_name: str) -> bool:
    lowered = (sheet_name or "").strip().lower()
    return any(marker in lowered for marker in IGNORED_SHEET_MARKERS)


def detect_layout(worksheet) -> str | None:
    """Content-based profile detection from the Arabic year anchors."""
    f4 = str(worksheet["F4"].value or "")
    d5 = str(worksheet["D5"].value or "")
    if ANCHOR_YEAR in f4:
        return LAYOUT_LEGACY
    if ANCHOR_YEAR in d5:
        return LAYOUT_RECENT
    return None


def _digit_text(value) -> str:
    """The digit characters of a header cell ('2 0' -> '20', 6.0 -> '6')."""
    if value is None:
        return ""
    text = str(value)
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(ch for ch in text if ch.isdigit())


def extract_sheet(wb_formulas, wb_values, sheet_name: str) -> dict:
    """One monthly sheet as a plain payload: header digits, the declared
    figures (cached value + cell + formula) and the extraction errors."""
    ws_f = wb_formulas[sheet_name]
    ws_v = wb_values[sheet_name]
    layout = detect_layout(ws_f)
    errors: list[str] = []
    if layout is None:
        errors.append("Layout de la feuille inconnu (anchors annee introuvables).")

    figures: dict[str, dict] = {}
    for key, (legacy_cell, recent_cell) in FIGURE_CELLS.items():
        cell_ref = (legacy_cell if layout == LAYOUT_LEGACY else recent_cell) if layout else None
        if not cell_ref:
            figures[key] = {"value": None, "cell": None, "formula": None}
            continue
        raw_formula = ws_f[cell_ref].value
        cached = ws_v[cell_ref].value
        is_formula = isinstance(raw_formula, str) and raw_formula.strip().startswith("=")
        if is_formula and cached is None:
            errors.append(
                f"Cellule {cell_ref}: formule sans valeur cachee — ouvrez la feuille et re-sauvegardez-la dans Excel."
            )
        value = cached
        if not is_formula and raw_formula is not None and cached is None:
            value = raw_formula
        figures[key] = {
            "value": value,
            "cell": cell_ref,
            "formula": raw_formula if is_formula else None,
        }

    year = "".join(_digit_text(figures[f"year_digit_{i}"]["value"]) for i in range(1, 5) if f"year_digit_{i}" in figures)
    month = "".join(_digit_text(figures[f"month_digit_{i}"]["value"]) for i in range(1, 3))
    tax_id = "".join(
        _digit_text(figures[f"tax_id_digit_{i}"]["value"]) for i in range(1, 8)
    ) + str(figures["tax_id_letter"]["value"] or "").strip().upper()

    return {
        "sheet": sheet_name,
        "month": month,
        "year": year,
        "tax_id": tax_id,
        "layout": layout,
        "errors": errors,
        "figures": figures,
    }


def monthly_sheet_names(wb_formulas) -> list[str]:
    """The workbook's monthly declaration sheets, in sheet order."""
    return [name for name in wb_formulas.sheetnames if is_monthly_sheet(name)]


RECAP_METRIC_HEADERS = {
    # first table (the TVA / timbre / TCL matrix)
    "HT 7%": "ht7",
    "TVA 7%": "tva7",
    "HT 19%": "ht19",
    "TVA 19%": "tva19",
    "TTC": "ttc",
    "TCL": "tcl",
    "AC": "ded_base",
    "TVA AC": "tva_deductible",
    "DT": "timbre",
    "P": "tva_due",
    # second table (the RS recap): S BUIT is the workbook's spelling of S BRUT
    "S BUIT": "gross",
    "S BRUT": "gross",
    "CNSS": "cnss",
    "S.IMPOS": "s_impos",
    "IRPP": "irpp",
    "CSS": "css",
    "TFP": "tfp",
    "FOPROLOS": "foprolos",
    "MT RS 1%": "rs1_base",
    "RS1%": "rs1",
    "MT RS 3%": "rs3_base",
    "RS3%": "rs3",
    "LOYER": "rs_loyer_base",
    "RS LOYER": "rs_loyer",
    "T A PYER": "total",
}


def extract_recap(wb_values) -> dict[int, dict[str, float]]:
    """The RECAP sheet as {month: {metric: value}}. The sheet carries TWO
    stacked tables (the TVA matrix, then the RS recap), each introduced by a
    "MOIS" header row: the columns are matched BY HEADER, never by position,
    and a month's figures from both tables merge. The TOTAL rows are skipped."""
    def normalize(text) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip().upper()

    recap_name = next(
        (name for name in wb_values.sheetnames if RECAP_SHEET_NAME in name.strip().lower()), None
    )
    if recap_name is None:
        return {}
    ws = wb_values[recap_name]

    recap: dict[int, dict[str, float]] = {}
    columns: dict[int, str] = {}
    month_col = None
    for row in range(1, (ws.max_row or 1) + 1):
        first = normalize(ws.cell(row=row, column=1).value)
        if first == "MOIS":
            # a new table's header row: remap the columns
            columns = {}
            month_col = None
            for column in range(1, (ws.max_column or 1) + 1):
                header = normalize(ws.cell(row=row, column=column).value)
                if header == "MOIS":
                    month_col = column
                elif header in RECAP_METRIC_HEADERS:
                    columns[column] = RECAP_METRIC_HEADERS[header]
            continue
        if month_col is None or not columns:
            continue
        if not first or first == "TOTAL":
            continue
        try:
            month = int(float(first))
        except (TypeError, ValueError):
            continue
        if not 1 <= month <= 12:
            continue
        month_figures = recap.setdefault(month, {})
        for column, metric in columns.items():
            value = ws.cell(row=row, column=column).value
            if value is None or metric in month_figures:
                continue
            try:
                month_figures[metric] = float(value)
            except (TypeError, ValueError):
                continue
    return recap


def build_sheet_copy(source_path: str, sheet_name: str) -> bytes:
    """A values-only single-sheet copy of the month's sheet: styles and
    merged cells kept, every formula replaced by its cached value, the other
    sheets removed."""
    import io

    import openpyxl

    wb = openpyxl.load_workbook(source_path, data_only=False)
    wb_values = openpyxl.load_workbook(source_path, data_only=True)
    target = None
    for name in list(wb.sheetnames):
        if name.strip().lower() == sheet_name.strip().lower():
            target = wb[name]
        else:
            wb.remove(wb[name])
    if target is None:
        raise ValueError(f"Feuille {sheet_name} introuvable dans le classeur.")

    values_ws = wb_values[sheet_name]
    for row in target.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and cell.value.strip().startswith("="):
                cached = values_ws[cell.coordinate].value
                cell.value = cached

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def extract_workbook(source_path: str) -> dict:
    """The full workbook payload: the monthly sheets and the RECAP rows."""
    import openpyxl

    wb_formulas = openpyxl.load_workbook(source_path, data_only=False)
    wb_values = openpyxl.load_workbook(source_path, data_only=True)
    sheets = [extract_sheet(wb_formulas, wb_values, name) for name in monthly_sheet_names(wb_formulas)]
    return {"sheets": sheets, "recap": extract_recap(wb_values)}
