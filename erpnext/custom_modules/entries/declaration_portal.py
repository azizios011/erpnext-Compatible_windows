# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Pure logic for the Déclaration Mensuelle's portal receipt ("Portail
e-tasrih" / Liquidé source): the payment deadline rule and the per-impôt
figures the checks compare.

The echeance is the 20th of the following month for Entreprises in the
télédéclaration system, the 28th for the others. When that day lands on a
Saturday, a Sunday or a Tunisian public holiday, the NEXT WORKING DAY is
shown as a WARNING ONLY — the stored echeance keeps the nominal rule date.

The fixed Tunisian public holidays are listed here; the movable religious
ones are not (documented limitation — extend the set when needed).
"""

from __future__ import annotations

from datetime import date, timedelta

# Fixed Tunisian public holidays (month, day).
TUNISIAN_PUBLIC_HOLIDAYS: set[tuple[int, int]] = {
    (1, 1),    # Nouvel an
    (3, 20),   # Fête de l'Indépendance
    (4, 9),    # Journée des martyrs
    (5, 1),    # Fête du travail
    (7, 25),   # Fête de la République
    (8, 13),   # Journée de la femme
    (10, 15),  # Journée de l'évacuation
    (12, 17),  # Journée de la Révolution
}

ECHEANCE_DAY_TELEDECLARE = 20
ECHEANCE_DAY_OTHER = 28

# The portal receipt's impôt labels (the child Select options) and the
# figure key each compares against.
PORTAL_IMPOTS = (
    "Retenue a la Source",
    "TFP",
    "FOPROLOS",
    "TVA",
    "Droit de timbre",
    "TCL",
    "Reliquat minimum de perception",
)

# impot -> the keys of the declared/calculated amounts the checks compare.
# None = the impôt has no counterpart on that side (Reliquat).
PORTAL_IMPOT_DECLARED: dict[str, str | None] = {
    "Retenue a la Source": "rs",
    "TFP": "tfp",
    "FOPROLOS": "foprolos",
    "TVA": "tva",
    "Droit de timbre": "timbre",
    "TCL": "tcl",
    "Reliquat minimum de perception": "reliquat",
}

# Tolerances when comparing against the portal's recomputed amounts: the
# portal rounding drifts per line but can sum wider on the total.
LIQUIDE_LINE_TOLERANCE = 0.005
LIQUIDE_TOTAL_TOLERANCE = 0.01


def is_tunisian_public_holiday(day: date) -> bool:
    return (day.month, day.day) in TUNISIAN_PUBLIC_HOLIDAYS


def is_working_day(day: date) -> bool:
    return day.weekday() < 5 and not is_tunisian_public_holiday(day)


def next_working_day(day: date) -> date:
    candidate = day + timedelta(days=1)
    while not is_working_day(candidate):
        candidate += timedelta(days=1)
    return candidate


def compute_echeance(annee: int, mois: int, teledeclaration: bool = True) -> date:
    """The payment deadline of a monthly declaration: the 20th of the
    following month (télédéclaration) or the 28th (the others), rolling into
    January of the next year after December."""
    if not 1 <= int(mois) <= 12:
        raise ValueError(f"mois {mois} hors 01-12")
    annee, mois = int(annee), int(mois)
    if mois == 12:
        next_month_year, next_month = annee + 1, 1
    else:
        next_month_year, next_month = annee, mois + 1
    day = ECHEANCE_DAY_TELEDECLARE if teledeclaration else ECHEANCE_DAY_OTHER
    return date(next_month_year, next_month, day)


def echeance_with_warning(annee: int, mois: int, teledeclaration: bool = True) -> tuple[date, str | None]:
    """(echeance, warning) — the warning names the next working day when the
    nominal deadline lands on a Saturday, Sunday or public holiday."""
    echeance = compute_echeance(annee, mois, teledeclaration)
    if is_working_day(echeance):
        return echeance, None
    working = next_working_day(echeance)
    return echeance, (
        f"L'echeance du {echeance.strftime('%d/%m/%Y')} tombe un jour non ouvrable "
        f"(week-end ou jour férié): le prochain jour ouvrable est le {working.strftime('%d/%m/%Y')}."
    )


def declared_impot_amounts(declared_rubriques: list[dict] | None) -> dict[str, float | None]:
    """The declared amounts per portal impôt, from the sheet's rubrique
    mapping ({code, montant}). RS lumps the whole F1_* family; the TVA is the
    declared position (collected - deductible), which the caller supplies
    separately under 'tva'."""
    rubriques = {row.get("code"): row.get("montant") for row in (declared_rubriques or [])}

    def family(prefixes: tuple[str, ...]) -> float | None:
        values = [rubriques.get(code) for code in prefixes if rubriques.get(code) is not None]
        return round(sum(float(v) for v in values), 3) if values else None

    tva = rubriques.get("F5_1_1")
    tva19 = rubriques.get("F5_1_3")
    ded = rubriques.get("F5_2_4")
    tva_position = None
    if tva is not None and tva19 is not None and ded is not None:
        tva_position = round(float(tva) + float(tva19) - float(ded), 3)

    return {
        "rs": family(("F1_1", "F1_3", "F1_4_1", "F1_6", "F1_17_1")),
        "tfp": rubriques.get("F2_1"),
        "foprolos": rubriques.get("F3_1"),
        "tva": tva_position,
        "timbre": rubriques.get("F7"),
        "tcl": family(("F9_3_1", "F9_3_2")),
        "reliquat": None,
    }


def calculated_impot_amounts(dm: dict | None) -> dict[str, float | None]:
    """The calculated amounts per portal impôt, from the Declaration
    Transaction payload's totals."""
    if not dm:
        return {"rs": None, "tfp": None, "foprolos": None, "tva": None, "timbre": None, "tcl": None, "reliquat": None}
    return {
        "rs": dm.get("total_rs"),
        "tfp": dm.get("total_tfp"),
        "foprolos": dm.get("total_foprolos"),
        "tva": dm.get("tva_a_payer"),
        "timbre": dm.get("total_timbre"),
        "tcl": dm.get("total_tcl"),
        "reliquat": None,
    }


def portal_line_totals(portal: dict | None) -> dict[str, float | None]:
    """The liquidated amount per comparison key (rs / tfp / foprolos / tva /
    timbre / tcl / reliquat), from the portal receipt's lines."""
    result = {key: None for key in set(PORTAL_IMPOT_DECLARED.values())}
    for line in (portal or {}).get("lines") or []:
        key = PORTAL_IMPOT_DECLARED.get(line.get("impot"))
        if key and line.get("total") is not None:
            result[key] = float(line["total"])
    return result
