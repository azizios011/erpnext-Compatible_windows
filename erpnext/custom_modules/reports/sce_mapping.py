# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Frappe-free SCE (Système Comptable des Entreprises — Tunisie) mapping for
the Bilan and the Etat de Resultat.

Code-first data: every rubrique carries the account-number PREFIXES it owns
on the plan comptable (the Tunisian PCT's standard first digits), its natural
balance side, and the contra prefixes (28x amortissements, 29x/39x/49x
provisions pour dépréciation) that net against it. The account set actually
present is whatever the Entreprise imported from its plan-comptable
workbook: accounts whose number matches NO prefix here are returned by
`classify_balances` as unmapped and the report lists them instead of
guessing.

One uniform arithmetic rule:
- an ASSET rubrique values `sum(debit - credit)` over its brut + net
  prefixes — the credit-heavy 28x/29x/39x/49x contra accounts subtract;
- a LIABILITY / CAPITAL rubrique values `sum(credit - debit)` over them —
  the debit-heavy contra accounts (e.g. 19 actions propres) subtract.

Overlap rule: an account number matches the rubrique owning its LONGEST
prefix, so an exact account prefix (e.g. 436666, a liability) can carve one
number out of a shorter asset prefix (4366, assets).
"""

from __future__ import annotations

# ── Bilan data ───────────────────────────────────────────────────────────────

BILAN_SECTIONS: list[str] = [
    "Actifs non courants",
    "Actifs courants",
    "Capitaux propres",
    "Passifs non courants",
    "Passifs courants",
]

# (key, label, section, side, brut prefixes, net prefixes)
# side "debit" = the asset side (value = sum(debit - credit));
# side "credit" = the liabilities / capital side (value = sum(credit - debit)).
BILAN_RUBRIQUES: list[dict] = [
    # ── Actifs non courants ──
    {"key": "immob_incorporelles", "label": "Immobilisations incorporelles",
     "section": "Actifs non courants", "side": "debit", "prefixes": ["21"], "nets": ["281", "291"]},
    {"key": "immob_corporelles", "label": "Immobilisations corporelles",
     "section": "Actifs non courants", "side": "debit",
     "prefixes": ["22", "23", "24", "25", "26"], "nets": ["282", "283", "284", "285", "293", "294", "295"]},
    {"key": "immob_financieres", "label": "Immobilisations financières",
     "section": "Actifs non courants", "side": "debit", "prefixes": ["27"], "nets": ["287", "297"]},
    {"key": "actifs_non_courants_autres", "label": "Autres actifs non courants",
     "section": "Actifs non courants", "side": "debit", "prefixes": ["19"], "nets": []},
    # ── Actifs courants ──
    {"key": "stocks", "label": "Stocks et en-cours",
     "section": "Actifs courants", "side": "debit", "prefixes": ["3"], "nets": ["39"]},
    {"key": "clients", "label": "Clients et comptes rattachés",
     "section": "Actifs courants", "side": "debit", "prefixes": ["41"], "nets": ["491"]},
    {"key": "actifs_courants_autres", "label": "Autres actifs courants",
     "section": "Actifs courants", "side": "debit", "prefixes": ["42", "45", "46", "47", "4366"], "nets": ["496", "497", "498"]},
    {"key": "placements", "label": "Placements",
     "section": "Actifs courants", "side": "debit", "prefixes": ["50"], "nets": []},
    {"key": "liquidites", "label": "Liquidités et équivalents",
     "section": "Actifs courants", "side": "debit", "prefixes": ["51", "53", "54", "58"], "nets": []},
    # ── Capitaux propres ──
    {"key": "capital", "label": "Capital",
     "section": "Capitaux propres", "side": "credit", "prefixes": ["10"], "nets": []},
    {"key": "reserves", "label": "Réserves",
     "section": "Capitaux propres", "side": "credit", "prefixes": ["11"], "nets": []},
    {"key": "capitaux_autres", "label": "Autres capitaux propres",
     "section": "Capitaux propres", "side": "credit", "prefixes": ["14"], "nets": []},
    {"key": "reportes", "label": "Résultats reportés (report à nouveau)",
     "section": "Capitaux propres", "side": "credit", "prefixes": ["12"], "nets": []},
    {"key": "resultat_exercice", "label": "Résultat de l'exercice",
     "section": "Capitaux propres", "side": "credit", "prefixes": [], "nets": []},
    # ── Passifs non courants ──
    {"key": "emprunts", "label": "Emprunts et dettes auprès des établissements de crédit",
     "section": "Passifs non courants", "side": "credit", "prefixes": ["16"], "nets": []},
    {"key": "passifs_financiers", "label": "Autres passifs financiers",
     "section": "Passifs non courants", "side": "credit", "prefixes": ["17", "18"], "nets": []},
    {"key": "provisions", "label": "Provisions pour risques et charges",
     "section": "Passifs non courants", "side": "credit", "prefixes": ["15"], "nets": []},
    # ── Passifs courants ──
    {"key": "fournisseurs", "label": "Fournisseurs et comptes rattachés",
     "section": "Passifs courants", "side": "credit", "prefixes": ["40"], "nets": []},
    {"key": "passifs_courants_autres", "label": "Autres passifs courants",
     "section": "Passifs courants", "side": "credit",
     "prefixes": ["42", "43", "44", "4365", "436666", "4367", "437", "47"], "nets": []},
    {"key": "concours", "label": "Concours bancaires courants",
     "section": "Passifs courants", "side": "credit", "prefixes": ["56", "519"], "nets": []},
]

# The computed bilan rubrique (class 7 minus class 6 balance).
RESULTAT_KEY = "resultat_exercice"

# The two grand totals.
ACTIF_SECTIONS = ("Actifs non courants", "Actifs courants")
PASSIF_SECTIONS = ("Capitaux propres", "Passifs non courants", "Passifs courants")

# ── Etat de Resultat data ────────────────────────────────────────────────────

ETAT_SECTIONS: list[str] = [
    "Produits d'exploitation",
    "Charges d'exploitation",
    "Résultat",
    "Éléments financiers et ordinaires",
]

ETAT_RUBRIQUES: list[dict] = [
    # (key, label, section, side, prefixes) — side "credit" = a produit,
    # "debit" = a charge; the computed cascade rows carry no prefixes.
    {"key": "revenus", "label": "Chiffre d'affaires (ventes, revenus)",
     "section": "Produits d'exploitation", "side": "credit", "prefixes": ["70", "71"]},
    {"key": "production_immobilisee", "label": "Production immobilisée",
     "section": "Produits d'exploitation", "side": "credit", "prefixes": ["72"]},
    {"key": "autres_produits", "label": "Autres produits d'exploitation (variations, reprises)",
     "section": "Produits d'exploitation", "side": "credit", "prefixes": ["73", "75", "78"]},
    {"key": "variation_stock", "label": "Variation des stocks",
     "section": "Charges d'exploitation", "side": "debit", "prefixes": ["603"]},
    {"key": "achats_marchandises", "label": "Achats de marchandises vendues",
     "section": "Charges d'exploitation", "side": "debit", "prefixes": ["607"]},
    {"key": "achats_approvisionnement", "label": "Achats de matières et approvisionnements consommés",
     "section": "Charges d'exploitation", "side": "debit", "prefixes": ["601", "602", "608", "609"]},
    {"key": "autres_charges", "label": "Services extérieurs et autres charges d'exploitation",
     "section": "Charges d'exploitation", "side": "debit", "prefixes": ["61", "62", "63", "65"]},
    {"key": "charges_personnel", "label": "Charges de personnel",
     "section": "Charges d'exploitation", "side": "debit", "prefixes": ["64"]},
    {"key": "dotations", "label": "Dotations aux amortissements et provisions",
     "section": "Charges d'exploitation", "side": "debit", "prefixes": ["68"]},
    # ── the computed cascade ──
    {"key": "resultat_exploitation", "label": "RÉSULTAT D'EXPLOITATION",
     "section": "Résultat", "side": "credit", "prefixes": None},
    {"key": "charges_financieres", "label": "Charges financières",
     "section": "Éléments financiers et ordinaires", "side": "debit", "prefixes": ["67"]},
    {"key": "produits_placements", "label": "Produits de placements et financiers",
     "section": "Éléments financiers et ordinaires", "side": "credit", "prefixes": ["77"]},
    {"key": "autres_gains_pertes", "label": "Autres gains et pertes ordinaires",
     "section": "Éléments financiers et ordinaires", "side": "credit", "prefixes": ["79"]},
    {"key": "impot_benefice", "label": "Impôt sur le bénéfice",
     "section": "Éléments financiers et ordinaires", "side": "debit", "prefixes": ["69"]},
    {"key": "resultat_ordinaire", "label": "RÉSULTAT ORDINAIRE APRÈS IMPÔT",
     "section": "Éléments financiers et ordinaires", "side": "credit", "prefixes": None},
    {"key": "elements_extraordinaires", "label": "Éléments extraordinaires",
     "section": "Éléments financiers et ordinaires", "side": "credit", "prefixes": None},
    {"key": "modifications_comptables", "label": "Modifications comptables sur éléments extraordinaires précédents",
     "section": "Éléments financiers et ordinaires", "side": "credit", "prefixes": None},
    {"key": "resultat_net", "label": "RÉSULTAT NET",
     "section": "Éléments financiers et ordinaires", "side": "credit", "prefixes": None},
]


def _prefix_owner_index(rubriques: list[dict]) -> dict[str, tuple[dict, str]]:
    """prefix -> (rubrique, kind) with the LONGEST prefix owning a number:
    kind "brut" for the rubrique's own prefixes, "net" for its contra
    prefixes. Ties cannot happen (a prefix maps to one rubrique)."""
    index: dict[str, tuple[dict, str]] = {}
    for rubrique in rubriques:
        for prefix in rubrique.get("prefixes") or []:
            index[prefix] = (rubrique, "brut")
        for prefix in rubrique.get("nets") or []:
            index[prefix] = (rubrique, "net")
    return index


def _owner_of(number: str, index: dict[str, tuple[dict, str]]) -> tuple[dict, str] | None:
    """The rubrique owning the number via its LONGEST matching prefix."""
    best: tuple[dict, str] | None = None
    best_length = -1
    for prefix, owner in index.items():
        if number.startswith(prefix) and len(prefix) > best_length:
            best, best_length = owner, len(prefix)
    return best


def classify_balances(
    balances: dict[str, dict],
    rubriques: list[dict],
    ignore_classes: tuple[str, ...] = (),
) -> tuple[dict[str, float], list[dict]]:
    """Spread the per-account net balances over the rubriques.

    balances: {account_number: {"debit": x, "credit": y}} (the raw sums, not
    netted). ignore_classes: first digits of the accounts the REPORT absorbs
    elsewhere (the Bilan nets classes 6 and 7 into the resultat de
    l'exercice; the Etat only reads classes 6 and 7) — those never appear in
    the unmapped list. Returns ({rubrique key: value}, [unmapped rows]) —
    the unmapped rows are the accounts with a balance beyond the rounding
    tolerance whose number matches no prefix: {number, debit, credit, net}."""
    index = _prefix_owner_index(rubriques)
    values: dict[str, float] = {}
    unmapped: list[dict] = []
    for number in sorted(balances):
        movement = balances[number]
        debit = float(movement.get("debit") or 0)
        credit = float(movement.get("credit") or 0)
        net = round(debit - credit, 3)
        if number[:1] in ignore_classes:
            continue
        owner = _owner_of(number, index)
        if owner is None:
            if abs(net) > 0.0005:
                unmapped.append(
                    {"number": number, "debit": round(debit, 3), "credit": round(credit, 3), "net": net}
                )
            continue
        rubrique = owner[0]
        side = rubrique["side"]
        # one polarity for brut AND net prefixes: on the debit side every
        # account contributes debit - credit (the credit-heavy 28x/39x/49x
        # contra accounts subtract naturally); on the credit side
        # credit - debit (the debit-contra accounts subtract)
        if side == "debit":
            contribution = debit - credit
        else:
            contribution = credit - debit
        values[rubrique["key"]] = round(values.get(rubrique["key"], 0.0) + contribution, 3)
    return values, unmapped


def variation(current: float | None, previous: float | None) -> tuple[float | None, float | None]:
    """(Variation, Variation %) — blank when neither exercice carries a
    figure; the percentage reads against |N-1|."""
    if current is None and previous is None:
        return None, None
    variation_value = round((current or 0.0) - (previous or 0.0), 3)
    if previous is None or abs(previous) < 0.0005:
        return variation_value, None
    return variation_value, round(variation_value / abs(previous) * 100, 3)


def build_bilan(
    calcule_n: dict[str, float] | None,
    calcule_n1: dict[str, float] | None,
    tolerance: float = 0.0005,
) -> dict:
    """The Bilan grid for one (N, N-1) pair of balance maps.

    N / N-1: {account_number: {debit, credit}} (None = no exercice, blank
    column). Returns the sectioned rows, the grand totals and the equilibre
    verdict. The resultat de l'exercice is the class 7 minus class 6
    balance of the N balances."""
    values_n, unmapped_n = classify_balances(
        calcule_n or {}, BILAN_RUBRIQUES, ignore_classes=("6", "7")
    )
    values_n1, unmapped_n1 = classify_balances(
        calcule_n1 or {}, BILAN_RUBRIQUES, ignore_classes=("6", "7")
    )

    # the resultat de l'exercice: the class 7 (produits) credit position over
    # the class 6 (charges) debit position, through the Etat's prefixed
    # rubriques
    produits, _unmapped = classify_balances(
        calcule_n or {}, [r for r in ETAT_RUBRIQUES if r["side"] == "credit" and r["prefixes"]],
        ignore_classes=("1", "2", "3", "4", "5", "8", "9"),
    )
    charges, _unmapped = classify_balances(
        calcule_n or {}, [r for r in ETAT_RUBRIQUES if r["side"] == "debit" and r["prefixes"]],
        ignore_classes=("1", "2", "3", "4", "5", "8", "9"),
    )
    produits_total = round(sum(produits.values()), 3)
    charges_total = round(sum(charges.values()), 3)
    values_n[RESULTAT_KEY] = round(produits_total - charges_total, 3)

    # the section totals, keyed section -> totals, drive both the rows and
    # the grand totals
    section_totals: dict[str, dict] = {}
    for section in BILAN_SECTIONS:
        rubrique_rows = [
            {"exercice_n": values_n.get(r["key"]), "exercice_n1": values_n1.get(r["key"])}
            for r in BILAN_RUBRIQUES
            if r["section"] == section
        ]
        section_totals[section] = totals_row(rubrique_rows)

    rows: list[dict] = []
    for section in BILAN_SECTIONS:
        rows.append({"row_type": "section", "rubrique": section})
        for rubrique in BILAN_RUBRIQUES:
            if rubrique["section"] != section:
                continue
            key = rubrique["key"]
            current = values_n.get(key)
            previous = values_n1.get(key)
            variation_value, variation_pct = variation(current, previous)
            rows.append(
                {
                    "row_type": "rubrique",
                    "key": key,
                    "rubrique": rubrique["label"],
                    "section": section,
                    "exercice_n": current,
                    "exercice_n1": previous,
                    "variation": variation_value,
                    "variation_pct": variation_pct,
                }
            )
        totals = section_totals[section]
        rows.append(
            {
                "row_type": "section_total",
                "rubrique": f"Total {section}",
                "exercice_n": totals["exercice_n"],
                "exercice_n1": totals["exercice_n1"],
                "variation": totals["variation"],
                "variation_pct": totals["variation_pct"],
            }
        )

    grand = grand_totals_row(section_totals)
    actif_total = grand["exercice_n"]["actif"]
    passif_total = grand["exercice_n"]["passif"]
    equilibre = abs(actif_total - passif_total) <= tolerance
    return {
        "rows": rows,
        "totals": grand,
        "section_totals": section_totals,
        "total_actif_n": actif_total,
        "total_passif_n": passif_total,
        "equilibre": equilibre,
        "difference": round(actif_total - passif_total, 3),
        "unmapped": {"n": unmapped_n, "n1": unmapped_n1},
    }


def grand_totals_row(section_totals: dict[str, dict]) -> dict:
    """The two grand totals per exercice column: Total Actifs vs Total
    Capitaux Propres + Passifs, with the equilibre verdict on N."""
    out = {}
    for key in ("exercice_n", "exercice_n1", "variation"):
        actif = round(sum(
            (section_totals.get(section) or {}).get(key) or 0 for section in ACTIF_SECTIONS
        ), 3)
        passif = round(sum(
            (section_totals.get(section) or {}).get(key) or 0 for section in PASSIF_SECTIONS
        ), 3)
        out[key] = {"actif": actif, "passif": passif}
    out["equilibre"] = abs(out["exercice_n"]["actif"] - out["exercice_n"]["passif"]) <= 0.0005
    return out


def totals_row(rows: list[dict]) -> dict:
    """Sum each exercice column over the rubrique rows (blank stays blank),
    and carry the variation over the sum."""
    out = {}
    for key in ("exercice_n", "exercice_n1"):
        values = [row.get(key) for row in rows if row.get(key) is not None]
        out[key] = round(sum(float(v) for v in values), 3) if values else None
    variation_value, variation_pct = variation(out["exercice_n"], out["exercice_n1"])
    out["variation"] = variation_value
    out["variation_pct"] = variation_pct
    return out


def build_etat(calcule_n: dict[str, float] | None, calcule_n1: dict[str, float] | None) -> dict:
    """The Etat de Resultat cascade for one (N, N-1) pair of balance maps."""
    values_n, unmapped_n = classify_balances(
        calcule_n or {}, ETAT_RUBRIQUES, ignore_classes=("1", "2", "3", "4", "5")
    )
    values_n1, unmapped_n1 = classify_balances(
        calcule_n1 or {}, ETAT_RUBRIQUES, ignore_classes=("1", "2", "3", "4", "5")
    )

    def cascade(values: dict[str, float]) -> None:
        """Fill the computed rows in place, per the SCE income cascade."""
        produits = round(sum(values.get(k) or 0 for k in
            ("revenus", "production_immobilisee", "autres_produits")), 3)
        charges = round(sum(values.get(k) or 0 for k in
            ("variation_stock", "achats_marchandises", "achats_approvisionnement",
             "autres_charges", "charges_personnel", "dotations")), 3)
        values["resultat_exploitation"] = round(produits - charges, 3)
        ordinary = round(
            values["resultat_exploitation"]
            - (values.get("charges_financieres") or 0)
            + (values.get("produits_placements") or 0)
            + (values.get("autres_gains_pertes") or 0)
            - (values.get("impot_benefice") or 0),
            3,
        )
        values["resultat_ordinaire"] = ordinary
        values["resultat_net"] = round(
            ordinary
            + (values.get("elements_extraordinaires") or 0)
            + (values.get("modifications_comptables") or 0),
            3,
        )
        return produits, charges

    produits_n, charges_n = cascade(values_n)
    cascade(values_n1)

    rows: list[dict] = []
    for section in ETAT_SECTIONS:
        rows.append({"row_type": "section", "rubrique": section})
        for rubrique in ETAT_RUBRIQUES:
            if rubrique["section"] != section:
                continue
            key = rubrique["key"]
            current, previous = values_n.get(key), values_n1.get(key)
            variation_value, variation_pct = variation(current, previous)
            rows.append(
                {
                    "row_type": "cascade" if rubrique["prefixes"] is None else "rubrique",
                    "key": key,
                    "rubrique": rubrique["label"],
                    "section": section,
                    "exercice_n": current,
                    "exercice_n1": previous,
                    "variation": variation_value,
                    "variation_pct": variation_pct,
                }
            )
    net = values_n.get("resultat_net") or 0.0
    return {
        "rows": rows,
        "resultat_net": round(net, 3),
        "benefice": net > 0.0005,
        "produits_n": produits_n,
        "charges_n": charges_n,
        "unmapped": {"n": unmapped_n, "n1": unmapped_n1},
    }
