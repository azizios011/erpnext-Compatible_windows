# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free checks over an imported Déclaration Mensuelle sheet.

Three families of controls, each producing rows of
{check_code, severity, message, declare, attendu, ecart}:

- **A. Sheet arithmetic** (`check_sheet_arithmetic`): the sheet must hold
  together on its own numbers — TVA7 = rate x HT7, TVA19 = rate x HT19,
  TVA due = collected - deductible - carry, TFP / FOPROLOS = the declared
  rate x the gross, TCL = rate x (HT7 + TVA7 + HT19 + TVA19) — the TTC
  WITHOUT the stamp duty, timbre = count x 1 DT, RS loyer = the declared
  rate x the rent base, and the grand total = the sum of all parts.
- **B. Sheet vs RECAP** (`check_recap`): the "RECAP 2026" row of the same
  month, the columns matched BY HEADER (never by position).
- **C. Declared vs the ledger** (`check_declaration`): the Declaration
  Transaction computed from the ledger for the same month — per rubrique
  base and amount plus the totals. Without one, a single Info control
  ("Non calculée") tells the accountant to compute it.

Tolerance: 0.005 TND — the employee fudged +-0.001 millimes on some rate
formulas. Status: Ecarts when any Erreur, Avertissements when only
Avertissements remain, Conforme otherwise (Info rows do not demote).
"""

from __future__ import annotations

SEVERITY_INFO = "Info"
SEVERITY_WARNING = "Avertissement"
SEVERITY_ERROR = "Erreur"

STATUS_CONFORME = "Conforme"
STATUS_WARNINGS = "Avertissements"
STATUS_ECARTS = "Ecarts"

TOLERANCE = 0.005

# The statutory rates, used when the sheet carries no declared-rate cell.
DEFAULT_RATES = {
    "tva7": 7.0,
    "tva19": 19.0,
    "tfp": 2.0,
    "foprolos": 1.0,
    "rs_loyer": 10.0,
    "tcl": 0.2,
    "timbre_piece": 1.0,
}

# The RECAP 2026 columns compared against the sheet, keyed by the metric the
# extraction produces (both RECAP tables: the TVA matrix and the RS recap).
RECAP_METRICS = (
    "ht7",
    "tva7",
    "ht19",
    "tva19",
    "ttc",
    "tcl",
    "ded_base",
    "tva_deductible",
    "timbre",
    "tva_due",
    "gross",
    "irpp",
    "css",
    "tfp",
    "foprolos",
    "rs1",
    "rs1_base",
    "rs3",
    "rs3_base",
    "rs_loyer",
    "rs_loyer_base",
    "total",
)

RECAP_METRIC_LABELS = {
    "ht7": "HT 7%",
    "tva7": "TVA 7%",
    "ht19": "HT 19%",
    "tva19": "TVA 19%",
    "ttc": "TTC",
    "tcl": "TCL",
    "ded_base": "Base TVA deductible (AC)",
    "tva_deductible": "TVA deductible",
    "timbre": "Droit de timbre",
    "tva_due": "TVA due (P)",
    "gross": "Masse salariale",
    "irpp": "IRPP (RS salaires)",
    "css": "CSS",
    "tfp": "TFP",
    "foprolos": "FOPROLOS",
    "rs1": "RS 1% fournisseurs",
    "rs1_base": "Base RS 1% fournisseurs",
    "rs3": "RS 3% honoraires",
    "rs3_base": "Base RS 3% honoraires",
    "rs_loyer": "RS loyers",
    "rs_loyer_base": "Base RS loyers",
    "total": "Total a payer",
}

# Rubriques whose declared BASE is compared with the ledger line's brut: the
# others either declare no base (CSS, TOTAL) or a base the DM computes
# differently (F5_2_4 brut is FIXE, F7's base is a document count).
DECLARATION_BASE_CODES = ("F1_1", "F1_4_1", "F1_6", "F1_17_1", "F2_1", "F3_1", "F5_1_1", "F5_1_3", "F9_3_1")


def _figure(sheet: dict, key: str) -> float | None:
    figure = (sheet.get("figures") or {}).get(key)
    if not figure:
        return None
    value = figure.get("value")
    if value is None or isinstance(value, str):
        return None
    return float(value)


def _declared_rate(sheet: dict, rate_key: str, default_key: str, rates: dict | None) -> float:
    """The sheet's own rate cell when it carries one ("use the declared
    rate"), else the statutory default. Rate cells hold fractions (0.07,
    0.002) or percents (7); both normalize to percents."""
    declared = _figure(sheet, rate_key)
    if declared:
        return declared * 100 if declared < 1 else declared
    return float(rates.get(default_key, DEFAULT_RATES.get(default_key, 0.0)))


def _control(code, severity, message, declare=None, attendu=None) -> dict:
    ecart = None
    if declare is not None and attendu is not None:
        ecart = round(float(declare) - float(attendu), 3)
    return {
        "check_code": code,
        "severity": severity,
        "message": message,
        "declare": declare,
        "attendu": attendu,
        "ecart": ecart,
    }


def _compare(code, message, declare, attendu, tolerance=TOLERANCE):
    """One Erreur control when the two figures both exist and drift beyond
    the tolerance; None when they agree or either side is missing."""
    if declare is None or attendu is None:
        return None
    ecart = round(float(declare) - float(attendu), 3)
    if abs(ecart) <= tolerance:
        return None
    return _control(code, SEVERITY_ERROR, message, declare, attendu)


def _percent(value: float) -> str:
    return f"{value:.3f}"


def check_sheet_arithmetic(sheet: dict, rates: dict | None = None) -> list[dict]:
    """A. The sheet against its own numbers."""
    rates = rates or {}
    controls: list[dict] = []

    ht7, tva7 = _figure(sheet, "ht7"), _figure(sheet, "tva7")
    ht19, tva19 = _figure(sheet, "ht19"), _figure(sheet, "tva19")
    controls.append(
        _compare(
            "TVA7_CALC",
            "TVA 7% != taux x chiffre d'affaires 7%",
            tva7,
            _declared_rate(sheet, "tva7_rate", "tva7", rates) / 100 * ht7 if ht7 is not None else None,
        )
    )
    controls.append(
        _compare(
            "TVA19_CALC",
            "TVA 19% != taux x chiffre d'affaires 19%",
            tva19,
            _declared_rate(sheet, "tva19_rate", "tva19", rates) / 100 * ht19 if ht19 is not None else None,
        )
    )

    collected = _figure(sheet, "tva_collectee")
    deductible = _figure(sheet, "tva_deductible")
    carry = _figure(sheet, "carry_prev") or 0.0
    due = _figure(sheet, "tva_due")
    computed_due = None
    if collected is not None and deductible is not None:
        computed_due = round(collected - deductible - carry, 3)
        if due is not None:
            # the sheet may present the position either way (payable or
            # credit marker); the magnitude must match the arithmetic
            controls.append(
                _compare(
                    "TVA_DUE_CALC",
                    "TVA due != collectee - deductible - credit reporte",
                    abs(due),
                    abs(computed_due),
                )
            )

    gross = _figure(sheet, "gross")
    tfp = _figure(sheet, "tfp")
    controls.append(
        _compare(
            "TFP_CALC",
            "TFP != taux declare x masse salariale",
            tfp,
            _declared_rate(sheet, "tfp_rate", "tfp", rates) / 100 * gross if gross is not None else None,
        )
    )
    foprolos = _figure(sheet, "foprolos")
    controls.append(
        _compare(
            "FOPROLOS_CALC",
            "FOPROLOS != taux declare x masse salariale",
            foprolos,
            _declared_rate(sheet, "foprolos_rate", "foprolos", rates) / 100 * gross if gross is not None else None,
        )
    )

    tcl = _figure(sheet, "tcl")
    if tcl is not None and ht7 is not None and ht19 is not None and tva7 is not None and tva19 is not None:
        # TCL applies to the TTC turnover WITHOUT the stamp duty
        ttc = ht7 + tva7 + ht19 + tva19
        controls.append(
            _compare(
                "TCL_CALC",
                "TCL != taux x TTC (HT + TVA, hors timbre)",
                tcl,
                _declared_rate(sheet, "tcl_rate", "tcl", rates) / 100 * ttc,
            )
        )

    timbre = _figure(sheet, "timbre")
    timbre_count = _figure(sheet, "timbre_count")
    piece_rate = float(rates.get("timbre_piece", DEFAULT_RATES["timbre_piece"]))
    controls.append(
        _compare(
            "TIMBRE_CALC",
            "Droit de timbre != nombre de pieces x 1.000 DT",
            timbre,
            timbre_count * piece_rate if timbre_count is not None else None,
        )
    )

    rs_loyer = _figure(sheet, "rs_loyer")
    rs_loyer_base = _figure(sheet, "rs_loyer_base")
    controls.append(
        _compare(
            "RS_LOYER_CALC",
            "RS loyers != taux declare x base loyers",
            rs_loyer,
            _declared_rate(sheet, "rs_loyer_rate", "rs_loyer", rates) / 100 * rs_loyer_base
            if rs_loyer_base is not None
            else None,
        )
    )

    total = _figure(sheet, "total")
    rs_total = _figure(sheet, "rs_total")
    if total is not None and rs_total is not None and computed_due is not None:
        parts = {
            "RS": rs_total,
            "TFP": tfp,
            "FOPROLOS": foprolos,
            "TVA due": computed_due,
            "Timbre": timbre,
            "TCL": tcl,
        }
        missing = [name for name, value in parts.items() if value is None]
        if not missing:
            expected_total = round(sum(parts.values()), 3)
            controls.append(
                _compare(
                    "TOTAL_CALC",
                    "Grand total != somme des parties (RS + TFP + FOPROLOS + TVA due + timbre + TCL)",
                    total,
                    expected_total,
                )
            )
    return [control for control in controls if control]


def check_recap(sheet: dict, recap_row: dict | None) -> list[dict]:
    """B. The sheet against the RECAP row of the same month (columns matched
    by header)."""
    if recap_row is None:
        return [_control("RECAP_ABSENTE", SEVERITY_INFO, "Ligne RECAP absente pour ce mois.")]
    controls: list[dict] = []
    for metric in RECAP_METRICS:
        expected = recap_row.get(metric)
        declared = _figure(sheet, metric)
        control = _compare(
            f"RECAP_{metric.upper()}",
            f"{RECAP_METRIC_LABELS[metric]}: feuille vs RECAP 2026",
            declared,
            expected,
        )
        if control:
            controls.append(control)
    return controls


# The Liquidé comparison: the portal receipt recomputes the amounts, so the
# tolerance is wider on the total than on each impot line.
LIQUIDE_LINE_TOLERANCE = 0.005
LIQUIDE_TOTAL_TOLERANCE = 0.01

LIQUIDE_LABELS = {
    "rs": "Retenue a la Source",
    "tfp": "TFP",
    "foprolos": "FOPROLOS",
    "tva": "TVA",
    "timbre": "Droit de timbre",
    "tcl": "TCL",
}


def check_declaration(sheet: dict, dm: dict | None, portal: dict | None = None) -> list[dict]:
    """C. The declared figures against the ledger-computed Declaration
    Transaction of the same month (per rubrique base and amount + totals),
    and — when the portal receipt is recorded — both Liquidé variances
    (Déclaré vs Liquidé, Calculé vs Liquidé) per impot line and total."""
    if dm is None:
        return [
            _control(
                "DM_ABSENTE",
                SEVERITY_INFO,
                "Declaration Transaction non calculee pour ce mois: lancez Calculer depuis la declaration (Entries).",
            )
        ]
    controls: list[dict] = []
    lines = {line.get("code"): line for line in (dm.get("lines") or [])}

    for mapping in sheet.get("rubriques") or []:
        code = mapping.get("code")
        if code == "TOTAL":
            continue
        line = lines.get(code)
        if not line:
            controls.append(
                _control(
                    f"DM_{code}_ABSENTE",
                    SEVERITY_WARNING,
                    f"La rubrique {code} declaree est absente de la Declaration Transaction du mois.",
                    mapping.get("montant"),
                )
            )
            continue
        if mapping.get("base") and code in DECLARATION_BASE_CODES:
            controls.append(
                _compare(
                    f"DM_{code}_BASE",
                    f"Rubrique {code}: base declaree vs brut du grand livre",
                    mapping.get("base"),
                    line.get("montant_brut"),
                )
            )
        controls.append(
            _compare(
                f"DM_{code}_MONTANT",
                f"Rubrique {code}: montant declare vs retenu du grand livre",
                mapping.get("montant"),
                line.get("retenu"),
            )
        )

    total = _figure(sheet, "total")
    controls.append(
        _compare("DM_TOTAL", "Grand total declare vs Total a payer de la Declaration Transaction", total, dm.get("total_a_payer"))
    )
    collected = _figure(sheet, "tva_collectee")
    controls.append(
        _compare("DM_TVA_COLLECTEE", "TVA collectee declaree vs TVA collectee du grand livre", collected, dm.get("tva_collectee"))
    )
    deductible = _figure(sheet, "tva_deductible")
    controls.append(
        _compare("DM_TVA_DEDUCTIBLE", "TVA deductible declaree vs TVA deductible du grand livre", deductible, dm.get("tva_deductible"))
    )
    due = _figure(sheet, "tva_due")
    if due is not None:
        # the ledger position: payable when positive, credit when zero
        expected = dm.get("tva_a_payer") if (dm.get("tva_a_payer") or 0) > 0 else dm.get("credit_suivant") or 0.0
        controls.append(
            _compare("DM_TVA_DUE", "TVA due declaree vs position TVA de la Declaration Transaction", abs(due), abs(expected or 0.0))
        )

    if portal:
        controls.extend(check_liquide(sheet, dm, portal))
    return [control for control in controls if control]


def check_liquide(sheet: dict, dm: dict | None, portal: dict) -> list[dict]:
    """The two Liquidé variances: the portal receipt's recomputed amounts vs
    the declared figures AND vs the ledger-computed ones — per impot line
    (0.005 TND) and on the total (0.01 TND)."""
    from erpnext.custom_modules.entries.declaration_portal import (
        LIQUIDE_LINE_TOLERANCE,
        LIQUIDE_TOTAL_TOLERANCE,
        calculated_impot_amounts,
        declared_impot_amounts,
        portal_line_totals,
    )

    controls: list[dict] = []
    declared = declared_impot_amounts(sheet.get("rubriques"))
    calculated = calculated_impot_amounts(dm)
    liquide = portal_line_totals(portal)
    liquide_total = (portal or {}).get("montant_liquide")

    for key, label in LIQUIDE_LABELS.items():
        liquidated = liquide.get(key)
        if liquidated is None:
            continue
        declared_value = declared.get(key)
        if declared_value is not None:
            controls.append(
                _compare(
                    f"LIQ_DECL_{key.upper()}",
                    f"{label}: montant declaré vs liquide (portail)",
                    liquidated,
                    declared_value,
                    tolerance=LIQUIDE_LINE_TOLERANCE,
                )
            )
        calculated_value = calculated.get(key)
        if calculated_value is not None and dm:
            controls.append(
                _compare(
                    f"LIQ_CALC_{key.upper()}",
                    f"{label}: montant calcule (grand livre) vs liquide (portail)",
                    liquidated,
                    calculated_value,
                    tolerance=LIQUIDE_LINE_TOLERANCE,
                )
            )

    if liquide_total is not None:
        declared_total = _figure(sheet, "total")
        controls.append(
            _compare(
                "LIQ_DECL_TOTAL",
                "Total a payer declaré vs liquide (portail)",
                liquide_total,
                declared_total,
                tolerance=LIQUIDE_TOTAL_TOLERANCE,
            )
        )
        if dm:
            controls.append(
                _compare(
                    "LIQ_CALC_TOTAL",
                    "Total a payer calcule (grand livre) vs liquide (portail)",
                    liquide_total,
                    dm.get("total_a_payer"),
                    tolerance=LIQUIDE_TOTAL_TOLERANCE,
                )
            )
    return [control for control in controls if control]





def status_from_controls(controls: list[dict]) -> str:
    """Ecarts when any Erreur, Avertissements when only Avertissements
    remain, Conforme otherwise (Info rows do not demote)."""
    severities = {control["severity"] for control in controls or []}
    if SEVERITY_ERROR in severities:
        return STATUS_ECARTS
    if SEVERITY_WARNING in severities:
        return STATUS_WARNINGS
    return STATUS_CONFORME


def run_checks(
    sheet: dict, recap_row: dict | None, dm: dict | None, rates: dict | None = None, portal: dict | None = None
) -> dict:
    """The check families over one extracted sheet."""
    controls: list[dict] = []
    controls.extend(check_sheet_arithmetic(sheet, rates))
    controls.extend(check_recap(sheet, recap_row))
    controls.extend(check_declaration(sheet, dm, portal))
    return {"controls": controls, "status": status_from_controls(controls)}
