# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Ledger-driven Déclaration Mensuelle engine (goal: the Axeane DM over the
Ecriture Comptable ledger).

Structure follows reports/imported_entries_logic.py: a frappe-free pure core
(everything unit-testable, no frappe import at module level) plus thin frappe
adapters and the whitelisted workflow methods. The adapters import frappe
lazily inside their bodies.

Month m reads the Ecriture Comptable rows of the context Entreprise/Exercice
whose posting_date falls inside calendar month m of the exercice's year. The
Exercice must be calendar-aligned (Jan 1 .. Dec 31 of its annee) — the CPR
comparative grid is a calendar-year matrix.

Every rate operation rounds ROUND_HALF_UP to 3 decimals (millimes).

The module binds frappe ONLY for the whitelisted workflow decorators below;
the pure core never touches it, so the frappe-free tests satisfy the import
with a stub and run without a site.
"""

from __future__ import annotations

import html
import frappe
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

LEDGER_DOCTYPE = "Ecriture Comptable"
DM_DOCTYPE = "Declaration Transaction"
DM_LINE_DOCTYPE = "Declaration Transaction Rubrique"
FAMILLE_DOCTYPE = "Famille Declaration"
RUBRIQUE_DOCTYPE = "Rubrique Declaration"
MENSUELLE_DOCTYPE = "Mensuelle"

STATUS_BROUILLON = "Brouillon"
STATUS_CLOTURE = "Cloture"
STATUS_DEPOSE = "Depose"

TYPE_PRINCIPALE = "Principale"
TYPE_COMPLEMENTAIRE = "Complementaire"

# The rubrique codes whose withheld amount is compared to brut x taux (the
# ledger-vs-rate difference shown to the accountant) and the TCL rule, which
# applies the local rate to the TTC turnover WITHOUT the stamp duty:
# 0.2% x (F5_1_1 brut + F5_1_1 retenu + F5_1_3 brut + F5_1_3 retenu).
THEORETICAL_BRUT_TAUX_CODES = ("F1_4_1", "F1_17_1", "F2_1", "F3_1")
TCL_THEORETICAL_CODE = "F9_3_1"
TCL_BASE_CODES = ("F5_1_1", "F5_1_3")

TVA_COLLECTEE_CODES = ("F5_1_1", "F5_1_2", "F5_1_3", "F5_3_1")
TVA_DEDUCTIBLE_PREFIX = "F5_2_"
RS_PREFIX = "F1_"

# Retenue TVA code the engine warns about when the month carries one.
RETENUE_TVA_CODE = "F5_3_1"

# Account-number prefixes whose month movements must be covered by a
# rubrique, else the engine warns (Declaration-family accounts).
WATCH_PREFIXES = ("432", "436", "437")


# ── pure core ────────────────────────────────────────────────────────────────


def rate3(value) -> float:
    """ROUND_HALF_UP to 3 decimals (millimes), on every rate operation."""
    return float(Decimal(str(float(value or 0))).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))


def month_bounds(annee: int, mois: int) -> tuple[date, date]:
    """The calendar month [first day, last day] of annee/mois."""
    if not 1 <= int(mois) <= 12:
        raise ValueError(f"mois {mois} hors 01-12")
    annee = int(annee)
    mois = int(mois)
    start = date(annee, mois, 1)
    if mois == 12:
        end = date(annee, 12, 31)
    else:
        end = date(annee, mois + 1, 1) - timedelta(days=1)
    return start, end


def assert_calendar_aligned(date_debut, date_fin, annee: int) -> None:
    """The CPR grid is a calendar-year matrix: the exercice must run Jan 1 to
    Dec 31 of its year, else the monthly partition is meaningless."""
    annee = int(annee)
    start = date_debut if isinstance(date_debut, date) else date.fromisoformat(str(date_debut)[:10])
    end = date_fin if isinstance(date_fin, date) else date.fromisoformat(str(date_fin)[:10])
    if (start.year, start.month, start.day) != (annee, 1, 1) or (end.year, end.month, end.day) != (
        annee,
        12,
        31,
    ):
        raise ValueError(
            f"L'exercice {annee} n'est pas aligne sur l'annee civile "
            f"({start.isoformat()} - {end.isoformat()}): la declaration mensuelle le refuse."
        )


def _interval_sums(balances: dict, intervals: list, sens: str) -> tuple[float, list[str]]:
    """(sum, row names) of the balances whose account number falls in the
    intervals, on the configured side (DEBIT sums debit, CREDIT sums credit)."""
    from erpnext.custom_modules.organization.account_interval import match_intervals

    total = 0.0
    rows: list[str] = []
    for number, movement in balances.items():
        if not match_intervals(number, intervals):
            continue
        side = float(movement.get(sens.lower()) or 0)
        total += side
        rows.extend(movement.get("rows") or [])
    return rate3(total), sorted(set(rows))


def compute_rubrique_line(rubrique: dict, balances: dict) -> dict:
    """One DM line from its config and the month's balances.

    brut: COMPTE sums the configured side of comptes_brut, RETENU_TAUX derives
    it backwards from the withheld tax (retenu / (taux/100)), FIXE is 0.
    retenu: COMPTE sums comptes_retenu, BRUT_TAUX applies the rate to the
    computed brut, FIXE is 0.
    """
    code = rubrique["code"]
    taux = float(rubrique.get("taux") or 0)
    brut_intervals = [tuple(i) for i in (rubrique.get("comptes_brut") or [])]
    retenu_intervals = [tuple(i) for i in (rubrique.get("comptes_retenu") or [])]

    brut_sum, brut_rows = (0.0, [])
    if rubrique.get("type_calcul_brut") == "COMPTE":
        brut_sum, brut_rows = _interval_sums(balances, brut_intervals, rubrique.get("sens_brut") or "DEBIT")
    retenu_sum, retenu_rows = (0.0, [])
    if rubrique.get("type_calcul_retenu") == "COMPTE":
        retenu_sum, retenu_rows = _interval_sums(balances, retenu_intervals, rubrique.get("sens_retenu") or "CREDIT")

    brut_type = rubrique.get("type_calcul_brut")
    retenu_type = rubrique.get("type_calcul_retenu")
    if brut_type == "COMPTE":
        brut = brut_sum
    elif brut_type == "RETENU_TAUX":
        if taux <= 0:
            raise ValueError(f"{code}: RETENU_TAUX exige un taux > 0")
        brut = rate3(retenu_sum / (taux / 100))
    else:
        brut = 0.0

    if retenu_type == "COMPTE":
        retenu = retenu_sum
    elif retenu_type == "BRUT_TAUX":
        if brut_type == "RETENU_TAUX":
            raise ValueError(f"{code}: brut RETENU_TAUX et retenu BRUT_TAUX sont circulaires")
        retenu = rate3(brut * (taux / 100)) if taux > 0 else 0.0
    else:
        retenu = 0.0

    rows = sorted(set(brut_rows) | set(retenu_rows))
    return {
        "code": code,
        "famille": rubrique.get("famille") or "",
        "famille_order": rubrique.get("famille_order") or 0,
        "famille_libelle": rubrique.get("famille_libelle") or "",
        "libelle": rubrique.get("libelle") or code,
        "taux": taux,
        "montant_brut": rate3(brut),
        "retenu": rate3(retenu),
        "retenu_theorique": 0.0,
        "ecart_theorique": 0.0,
        "nb_ecritures": len(rows),
        "ecritures": ", ".join(rows),
        "_brut_rows": brut_rows,
        "_retenu_rows": retenu_rows,
        "_taux": taux,
    }


def compute_rubriques(rubriques: list[dict], balances: dict) -> list[dict]:
    """All DM lines, in famille then code order, plus the theoretical pass:
    brut x taux for the comparison codes, and the TCL rule over the TVA
    turnover (TTC without the stamp duty)."""
    lines = [compute_rubrique_line(rubrique, balances) for rubrique in rubriques]
    lines.sort(key=lambda line: (line.get("famille_order") or 0, line["code"]))
    by_code = {line["code"]: line for line in lines}

    # the theoretical pass: brut x taux for the comparison codes — the
    # ecart column only means something where a rule exists
    for line in lines:
        if line["code"] in THEORETICAL_BRUT_TAUX_CODES:
            line["retenu_theorique"] = rate3(line["montant_brut"] * (line["_taux"] / 100))
            line["ecart_theorique"] = rate3(line["retenu"] - line["retenu_theorique"])

    tcl_line = by_code.get(TCL_THEORETICAL_CODE)
    if tcl_line:
        base = 0.0
        for code in TCL_BASE_CODES:
            base_line = by_code.get(code)
            if base_line:
                base += base_line["montant_brut"] + base_line["retenu"]
        tcl_line["retenu_theorique"] = rate3(tcl_line["_taux"] / 100 * base)
        tcl_line["ecart_theorique"] = rate3(tcl_line["retenu"] - tcl_line["retenu_theorique"])
    return lines


def retenu_of(lines: list[dict], code: str) -> float:
    for line in lines:
        if line["code"] == code:
            return line["retenu"]
    return 0.0


def compute_totals(lines: list[dict], credit_anterieur: float) -> dict:
    """The DM totals: TVA position with the carry (negative = credit) and the
    grand total a payer."""
    tva_collectee = rate3(sum(retenu_of(lines, code) for code in TVA_COLLECTEE_CODES))
    tva_deductible = rate3(
        sum(line["retenu"] for line in lines if line["code"].startswith(TVA_DEDUCTIBLE_PREFIX))
    )
    net = rate3(tva_collectee - tva_deductible + float(credit_anterieur or 0))
    if net > 0:
        tva_a_payer, credit_suivant = net, 0.0
    else:
        tva_a_payer, credit_suivant = 0.0, rate3(-net)
    total_rs = rate3(sum(line["retenu"] for line in lines if line["code"].startswith(RS_PREFIX)))
    total_tfp = rate3(retenu_of(lines, "F2_1"))
    total_foprolos = rate3(retenu_of(lines, "F3_1"))
    total_timbre = rate3(retenu_of(lines, "F7"))
    total_tcl = rate3(retenu_of(lines, "F9_3_1") + retenu_of(lines, "F9_3_2"))
    total_a_payer = rate3(
        total_rs + total_tfp + total_foprolos + tva_a_payer + total_timbre + total_tcl
    )
    return {
        "tva_collectee": tva_collectee,
        "tva_deductible": tva_deductible,
        "tva_a_payer": tva_a_payer,
        "credit_suivant": credit_suivant,
        "total_rs": total_rs,
        "total_tfp": total_tfp,
        "total_foprolos": total_foprolos,
        "total_timbre": total_timbre,
        "total_tcl": total_tcl,
        "total_a_payer": total_a_payer,
    }


def uncovered_watch_accounts(balances: dict, rubriques: list[dict]) -> list[dict]:
    """Month movements on 432*/436*/437* accounts covered by NO active
    rubrique interval (brut or retenu) — amounts the DM silently ignores."""
    from erpnext.custom_modules.organization.account_interval import match_intervals

    configured: list[tuple] = []
    for rubrique in rubriques:
        configured.extend(tuple(i) for i in (rubrique.get("comptes_brut") or []))
        configured.extend(tuple(i) for i in (rubrique.get("comptes_retenu") or []))

    uncovered = []
    for number in sorted(balances):
        if not number.startswith(WATCH_PREFIXES):
            continue
        if match_intervals(number, configured):
            continue
        movement = balances[number]
        uncovered.append(
            {
                "account_number": number,
                "movement": rate3(float(movement.get("debit") or 0) + float(movement.get("credit") or 0)),
            }
        )
    return uncovered


def build_avertissements(
    lines: list[dict],
    uncovered: list[dict],
    previous_month_missing: bool,
    previous_mois: int | None = None,
) -> list[str]:
    warnings: list[str] = []
    if uncovered:
        detail = ", ".join(f"{u['account_number']} ({u['movement']:.3f})" for u in uncovered)
        warnings.append(
            "Mouvements du mois sur des comptes 432/436/437 non couverts par une rubrique: " + detail
        )
    if previous_month_missing and previous_mois:
        warnings.append(
            f"Aucune declaration Depose pour le mois {int(previous_mois):02d}: "
            "des mois ont ete sautes (la premiere declaration d'un exercice peut demarrer sur n'importe quel mois)."
        )
    retenue_tva = retenu_of(lines, RETENUE_TVA_CODE)
    if retenue_tva:
        warnings.append(
            f"Retenue TVA 25% non nulle ({retenue_tva:.3f}): verifiez les marchés / achats >= 1000 DT."
        )
    return warnings


def compute_declaration_core(
    rubriques: list[dict],
    balances: dict,
    credit_anterieur: float,
    previous_month_missing: bool = False,
    previous_mois: int | None = None,
) -> dict:
    """The full pure computation: lines, totals, warnings."""
    lines = compute_rubriques(rubriques, balances)
    totals = compute_totals(lines, credit_anterieur)
    uncovered = uncovered_watch_accounts(balances, rubriques)
    avertissements = build_avertissements(lines, uncovered, previous_month_missing, previous_mois)
    return {"lines": lines, "avertissements": avertissements, "uncovered": uncovered, **totals}


# ── HTML renderers (frappe-free: stdlib escaping) ────────────────────────────


def render_rubriques_html(lines: list[dict], avertissements: list[str]) -> str:
    def esc(value) -> str:
        return html.escape(str(value if value is not None else ""))

    def money(value) -> str:
        return f"{float(value or 0):,.3f}".replace(",", " ")

    out = ['<div class="dm-rubriques">']
    if avertissements:
        items = "".join(f"<li>{esc(w)}</li>" for w in avertissements)
        out.append(
            '<div class="alert alert-warning dm-warnings" style="margin-bottom:12px;">'
            f'<strong>Avertissements</strong><ul style="margin:6px 0 0 18px;">{items}</ul></div>'
        )
    out.append('<table class="table table-bordered dm-table" style="margin-bottom:0;">')
    out.append(
        "<thead><tr><th>Code</th><th>Libelle</th>"
        '<th style="text-align:right;">Brut</th><th style="text-align:right;">Taux %</th>'
        '<th style="text-align:right;">Retenu</th><th style="text-align:right;">Theorique</th>'
        '<th style="text-align:right;">Ecart</th><th style="text-align:center;">Ecr.</th></tr></thead><tbody>'
    )
    current_famille: str | None = None
    for line in lines:
        if line["famille"] != current_famille:
            current_famille = line["famille"]
            label = line.get("famille_libelle") or current_famille
            out.append(
                f'<tr class="dm-famille-row"><td colspan="8" style="font-weight:600;'
                f'background:#f8f9fa;">Famille {esc(label)}</td></tr>'
            )
        clickable = line["nb_ecritures"] > 0
        row_attr = (
            f' class="dm-rubrique-row" style="cursor:pointer;" data-code="{esc(line["code"])}"'
            if clickable
            else ""
        )
        cells = (
            f"<td>{esc(line['code'])}</td><td>{esc(line['libelle'])}</td>"
            f'<td style="text-align:right;">{money(line["montant_brut"])}</td>'
            f'<td style="text-align:right;">{esc(line["taux"])}</td>'
            f'<td style="text-align:right;">{money(line["retenu"])}</td>'
            f'<td style="text-align:right;">{money(line["retenu_theorique"])}</td>'
            f'<td style="text-align:right;">{money(line["ecart_theorique"])}</td>'
            f'<td style="text-align:center;">{line["nb_ecritures"] or ""}</td>'
        )
        out.append(f"<tr{row_attr}>{cells}</tr>")
    out.append("</tbody></table></div>")
    out.append(
        '<p style="margin-top:6px;color:#8d99ae;font-size:12px;">'
        "Cliquez sur une ligne chiffrée pour voir les écritures qui la composent.</p>"
    )
    return "".join(out)


def render_totaux_html(totals: dict) -> str:
    def money(value) -> str:
        return f"{float(value or 0):,.3f}".replace(",", " ")

    cards = (
        ("TVA collectée", totals.get("tva_collectee"), "#eef6ee"),
        ("TVA déductible", totals.get("tva_deductible"), "#eef4fb"),
        ("TVA à payer", totals.get("tva_a_payer"), "#fdf2f2"),
        ("Crédit suivant", totals.get("credit_suivant"), "#eef4fb"),
        ("Total RS", totals.get("total_rs"), "#f7f7f7"),
        ("TFP", totals.get("total_tfp"), "#f7f7f7"),
        ("FOPROLOS", totals.get("total_foprolos"), "#f7f7f7"),
        ("Timbre", totals.get("total_timbre"), "#f7f7f7"),
        ("TCL", totals.get("total_tcl"), "#f7f7f7"),
        ("TOTAL À PAYER", totals.get("total_a_payer"), "#fff7e6"),
    )
    out = ['<div style="display:flex;flex-wrap:wrap;gap:10px;">']
    for label, value, bg in cards:
        bold = label in ("TVA à payer", "TOTAL À PAYER")
        out.append(
            f'<div style="background:{bg};border:1px solid #d1d8dd;border-radius:6px;'
            f'padding:8px 14px;min-width:140px;">'
            f'<div style="font-size:11px;color:#6b7280;text-transform:uppercase;">{html.escape(label)}</div>'
            f'<div style="font-size:16px;{"font-weight:700;" if bold else "font-weight:600;"}">'
            f"{money(value)}</div></div>"
        )
    out.append("</div>")
    return "".join(out)


# ── frappe adapters (lazy frappe import) ─────────────────────────────────────


def _frappe():
    import frappe

    return frappe


def _context():
    frappe = _frappe()
    from erpnext.custom_modules.organization.context import require_context, validate_exercice_open

    context = require_context()
    validate_exercice_open(context)
    return context


def _load_exercice(exercice: str) -> dict:
    frappe = _frappe()
    row = frappe.db.get_value(
        "Exercice", exercice, ["annee", "date_debut", "date_fin"], as_dict=True
    )
    if not row:
        raise ValueError(f"L'exercice {exercice} est introuvable.")
    return row


def _load_rubrique_config(entreprise: str) -> list[dict]:
    """Active rubriques of included familles, with their compte intervals as
    (account_number, upper_number) tuples — numbers, not names."""
    frappe = _frappe()
    familles = frappe.get_all(
        FAMILLE_DOCTYPE,
        filters={"entreprise": entreprise, "inclus": 1},
        fields=["name", "famille_code", "libelle"],
    )
    if not familles:
        return []
    by_name = {f.name: f for f in familles}
    rows = frappe.get_all(
        RUBRIQUE_DOCTYPE,
        filters={"entreprise": entreprise, "actif": 1, "famille": ("in", list(by_name))},
        fields=[
            "name",
            "code",
            "libelle",
            "famille",
            "taux",
            "type_calcul_brut",
            "sens_brut",
            "type_calcul_retenu",
            "sens_retenu",
        ],
        order_by="code asc",
    )
    compte_rows = frappe.get_all(
        "Rubrique Declaration Compte",
        filters={"parenttype": RUBRIQUE_DOCTYPE, "parent": ("in", [r.name for r in rows])},
        fields=["parent", "parentfield", "compte_de", "compte_a"],
    )
    numbers = frappe.get_all(
        "Chart of Account",
        filters={"entreprise": entreprise, "name": ("in", {c.compte_de for c in compte_rows} | {c.compte_a for c in compte_rows if c.compte_a})},
        fields=["name", "account_number"],
    )
    number_of = {n.name: (n.account_number or "").strip() for n in numbers}

    intervals: dict[str, dict[str, list]] = {}
    for row in compte_rows:
        de = number_of.get(row.compte_de, "")
        a = number_of.get(row.compte_a, "") if row.compte_a else ""
        if not de:
            continue
        intervals.setdefault(row.parent, {}).setdefault(row.parentfield, []).append((de, a))

    config: list[dict] = []
    for r in rows:
        famille = by_name.get(r.famille)
        config.append(
            {
                "name": r.name,
                "code": r.code,
                "libelle": r.libelle,
                "famille": famille.famille_code if famille else "",
                "famille_order": famille.code if famille else 0,
                "famille_libelle": famille.libelle if famille else "",
                "taux": r.taux,
                "type_calcul_brut": r.type_calcul_brut,
                "sens_brut": r.sens_brut,
                "type_calcul_retenu": r.type_calcul_retenu,
                "sens_retenu": r.sens_retenu,
                "comptes_brut": intervals.get(r.name, {}).get("comptes_brut", []),
                "comptes_retenu": intervals.get(r.name, {}).get("comptes_retenu", []),
            }
        )
    return config


def _load_month_balances(entreprise: str, exercice: str, annee: int, mois: int) -> dict:
    """account_number -> {debit, credit, rows} for the calendar month: sums
    aggregated by SQL, row names collected for the drill-down."""
    frappe = _frappe()
    start, end = month_bounds(annee, mois)
    sums = frappe.db.sql(
        f"""select account, sum(debit) as debit, sum(credit) as credit
            from `tab{LEDGER_DOCTYPE}`
            where entreprise = %(entreprise)s and exercice = %(exercice)s
              and posting_date >= %(start)s and posting_date <= %(end)s
            group by account""",
        {"entreprise": entreprise, "exercice": exercice, "start": start, "end": end},
        as_dict=True,
    )
    rows = frappe.get_all(
        LEDGER_DOCTYPE,
        filters=[
            ["entreprise", "=", entreprise],
            ["exercice", "=", exercice],
            ["posting_date", ">=", start],
            ["posting_date", "<=", end],
        ],
        fields=["name", "account"],
        order_by="name asc",
    )
    rows_by_account: dict[str, list[str]] = {}
    for row in rows:
        rows_by_account.setdefault(row.account, []).append(row.name)

    numbers = frappe.get_all(
        "Chart of Account",
        filters={"entreprise": entreprise, "name": ("in", {s.account for s in sums})},
        fields=["name", "account_number"],
    )
    number_of = {n.name: (n.account_number or "").strip() for n in numbers}

    balances: dict[str, dict] = {}
    for s in sums:
        number = number_of.get(s.account, "")
        if not number:
            continue
        balances[number] = {
            "debit": float(s.debit or 0),
            "credit": float(s.credit or 0),
            "rows": rows_by_account.get(s.account, []),
        }
    return balances


def _dm_name(exercice: str, mois: str, type_declaration: str) -> str:
    return f"DM-{exercice}-{mois}-{type_declaration}"


def _previous_principale(entreprise: str, exercice: str, mois: int):
    """The latest Principale strictly before mois: (name, credit_suivant) or
    None. Also returns whether ANY earlier declaration exists."""
    frappe = _frappe()
    rows = frappe.get_all(
        DM_DOCTYPE,
        filters={
            "entreprise": entreprise,
            "exercice": exercice,
            "type_declaration": TYPE_PRINCIPALE,
            "mois": ("<", f"{int(mois):02d}"),
        },
        fields=["name", "mois", "credit_suivant", "status"],
        order_by="mois desc",
        limit=1,
    )
    if not rows:
        return None
    return rows[0]


def _previous_mois_state(entreprise: str, exercice: str, mois: int) -> str:
    """'depose' | 'exists_not_depose' | 'missing' for mois-1's Principale."""
    if mois <= 1:
        return "depose"
    frappe = _frappe()
    rows = frappe.get_all(
        DM_DOCTYPE,
        filters={
            "entreprise": entreprise,
            "exercice": exercice,
            "type_declaration": TYPE_PRINCIPALE,
            "mois": f"{int(mois) - 1:02d}",
        },
        fields=["status"],
        limit=1,
    )
    if not rows:
        return "missing"
    return "depose" if rows[0].status == STATUS_DEPOSE else "exists_not_depose"


def _resolve_mensuelle(entreprise: str, exercice: str, annee: int, mois: int, mensuelle: str = "") -> str:
    """The Mensuelle document this DM belongs to: the explicit link when
    given, else the month's own Mensuelle upload."""
    frappe = _frappe()
    if mensuelle:
        owner = frappe.db.get_value(MENSUELLE_DOCTYPE, mensuelle, ["entreprise", "exercice"], as_dict=True)
        if not owner or owner.entreprise != entreprise or owner.exercice != exercice:
            raise ValueError(f"La Mensuelle {mensuelle} n'appartient pas au contexte comptable.")
        return mensuelle
    rows = frappe.get_all(
        MENSUELLE_DOCTYPE,
        filters={
            "entreprise": entreprise,
            "exercice": exercice,
            "period_month": f"{int(mois):02d}",
            "period_year": annee,
        },
        pluck="name",
        order_by="creation desc",
        limit=1,
    )
    return rows[0] if rows else ""


def _write_back_mensuelle(dm_name: str, mensuelle: str, status: str) -> None:
    frappe = _frappe()
    if not mensuelle:
        return
    entry_status = "Brouillon" if status == STATUS_BROUILLON else "Comptabilisee"
    frappe.db.set_value(
        MENSUELLE_DOCTYPE,
        mensuelle,
        {"entry": dm_name, "entry_doctype": DM_DOCTYPE, "entry_status": entry_status},
        update_modified=False,
    )


# ── whitelisted workflow ─────────────────────────────────────────────────────


def _throw(message: str) -> None:
    import frappe
    from frappe import _

    frappe.throw(_(message))


@frappe.whitelist(methods=["POST"])
def compute_declaration(mois: str, type_declaration: str = TYPE_PRINCIPALE, mensuelle: str = "") -> dict:
    """Create or recompute the Brouillon DM of (exercice, mois, type). Gated:
    month N needs month N-1 Depose (the first declaration of an exercice may
    be any month — a skipped month warns instead of refusing)."""
    frappe = _frappe()
    try:
        result = _compute_declaration(mois, type_declaration, mensuelle)
    except ValueError as error:
        _throw(str(error))
    return result


def _compute_declaration(mois: str, type_declaration: str, mensuelle: str) -> dict:
    frappe = _frappe()
    context = _context()
    entreprise, exercice = context["entreprise"], context["exercice"]

    mois_clean = f"{int(str(mois)):02d}"
    mois_int = int(mois_clean)
    if type_declaration not in (TYPE_PRINCIPALE, TYPE_COMPLEMENTAIRE):
        raise ValueError("type_declaration doit valoir Principale ou Complementaire")

    exercice_row = _load_exercice(exercice)
    assert_calendar_aligned(exercice_row.date_debut, exercice_row.date_fin, exercice_row.annee)

    config = _load_rubrique_config(entreprise)
    if not config:
        raise ValueError(
            "Aucune rubrique de declaration active pour ce contexte: chargez le modele standard "
            "(Familles / Rubriques de declaration)."
        )

    previous = _previous_mois_state(entreprise, exercice, mois_int)
    if previous == "exists_not_depose":
        raise ValueError(
            f"Le mois {mois_int - 1:02d} n'est pas Depose: cloturez puis deposez le mois precedent "
            "avant de calculer le suivant."
        )

    previous_principale = _previous_principale(entreprise, exercice, mois_int)
    credit_anterieur = -float(previous_principale.credit_suivant or 0) if previous_principale else 0.0
    if not previous_principale:
        # the first declaration of the exercice: the persisted carry (if the
        # accountant already saved one) wins over a recompute reset
        name = _dm_name(exercice, mois_clean, type_declaration)
        if frappe.db.exists(DM_DOCTYPE, name):
            credit_anterieur = float(
                frappe.db.get_value(DM_DOCTYPE, name, "report_credit_anterieur") or 0
            )

    has_earlier_declarations = bool(
        frappe.get_all(
            DM_DOCTYPE,
            filters={"entreprise": entreprise, "exercice": exercice, "mois": ("<", mois_clean)},
            limit=1,
        )
    )
    balances = _load_month_balances(entreprise, exercice, exercice_row.annee, mois_int)
    result = compute_declaration_core(
        config,
        balances,
        credit_anterieur,
        previous_month_missing=(previous == "missing" and has_earlier_declarations),
        previous_mois=mois_int - 1,
    )

    mensuelle_name = _resolve_mensuelle(entreprise, exercice, exercice_row.annee, mois_int, mensuelle)
    name = _dm_name(exercice, mois_clean, type_declaration)
    existing_status = frappe.db.get_value(DM_DOCTYPE, name, "status") if frappe.db.exists(DM_DOCTYPE, name) else None
    if existing_status and existing_status != STATUS_BROUILLON:
        raise ValueError(
            f"La declaration {name} est {existing_status}: dé-clôturez-la avant de recalculer."
        )

    values = {
        "entreprise": entreprise,
        "exercice": exercice,
        "mois": mois_clean,
        "annee": exercice_row.annee,
        "type_declaration": type_declaration,
        "status": STATUS_BROUILLON,
        "mensuelle": mensuelle_name,
        "report_credit_anterieur": rate3(credit_anterieur),
        "rubriques": [],
        "avertissements": "\n".join(result["avertissements"]),
        "rubriques_html": render_rubriques_html(result["lines"], result["avertissements"]),
        "totaux_html": render_totaux_html(result),
    }
    values.update(
        {k: result[k] for k in (
            "tva_collectee", "tva_deductible", "tva_a_payer", "credit_suivant",
            "total_rs", "total_tfp", "total_foprolos", "total_timbre", "total_tcl", "total_a_payer",
        )}
    )
    line_keys = (
        "code", "famille", "libelle", "taux", "montant_brut", "retenu",
        "retenu_theorique", "ecart_theorique", "nb_ecritures", "ecritures",
    )

    if existing_status:
        doc = frappe.get_doc(DM_DOCTYPE, name)
        for key, value in values.items():
            if key == "rubriques":
                doc.set("rubriques", [])
                continue
            doc.set(key, value)
        for line in result["lines"]:
            doc.append("rubriques", {k: line[k] for k in line_keys})
        doc.save()
    else:
        for line in result["lines"]:
            values["rubriques"].append({k: line[k] for k in line_keys})
        doc = frappe.get_doc({"doctype": DM_DOCTYPE, **values})
        doc.insert()

    _write_back_mensuelle(doc.name, mensuelle_name, STATUS_BROUILLON)
    return {"name": doc.name, **{k: result[k] for k in ("tva_a_payer", "credit_suivant", "total_a_payer")}}


def _require_dm(name: str):
    """The DM of the context only."""
    frappe = _frappe()
    from erpnext.custom_modules.organization.context import require_context

    context = require_context()
    doc = frappe.get_doc(DM_DOCTYPE, name)
    if doc.entreprise != context["entreprise"] or doc.exercice != context["exercice"]:
        raise ValueError(
            f"La declaration {name} appartient a un autre contexte comptable "
            f"({doc.entreprise} · {doc.exercice})."
        )
    return doc


@frappe.whitelist(methods=["POST"])
def cloture_declaration(name: str) -> dict:
    """Cloture: freeze the DM and stamp every ledger row it used
    (declaration_cloture), which locks them against edits and deletions."""
    frappe = _frappe()
    try:
        doc = _require_dm(name)
        if doc.status != STATUS_BROUILLON:
            raise ValueError(f"La declaration {name} est {doc.status}: seule une Brouillon peut etre cloturee.")

        rows: list[str] = []
        for line in doc.rubriques or []:
            rows.extend(x.strip() for x in (line.ecritures or "").split(",") if x.strip())
        rows = sorted(set(rows))
        for row in rows:
            owner = frappe.db.get_value(LEDGER_DOCTYPE, row, "declaration_cloture")
            if owner and owner != doc.name:
                raise ValueError(
                    f"L'ecriture {row} est deja verrouillee par {owner}: "
                    "dé-clôturez cette declaration d'abord."
                )
        for row in rows:
            frappe.db.set_value(LEDGER_DOCTYPE, row, "declaration_cloture", doc.name, update_modified=False)
        frappe.db.set_value(DM_DOCTYPE, doc.name, "status", STATUS_CLOTURE, update_modified=False)
        _write_back_mensuelle(doc.name, doc.mensuelle, STATUS_CLOTURE)
        return {"name": doc.name, "status": STATUS_CLOTURE, "rows_stamped": len(rows)}
    except ValueError as error:
        _throw(str(error))


@frappe.whitelist(methods=["POST"])
def decloture_declaration(name: str) -> dict:
    """Dé-clôture: only a Cloture DM with no LATER month computed (the ledger
    rows of a later month may already depend on this one)."""
    frappe = _frappe()
    try:
        doc = _require_dm(name)
        if doc.status != STATUS_CLOTURE:
            raise ValueError(f"La declaration {name} est {doc.status}: seules les Cloture se de-cloturent.")
        later = frappe.get_all(
            DM_DOCTYPE,
            filters={
                "entreprise": doc.entreprise,
                "exercice": doc.exercice,
                "mois": (">", doc.mois),
            },
            fields=["name", "mois"],
            order_by="mois asc",
            limit=1,
        )
        if later:
            raise ValueError(
                f"Le mois {later[0].mois} est deja calcule ({later[0].name}): "
                "de-cloturez les mois suivants d'abord."
            )
        frappe.db.sql(
            f"""update `tab{LEDGER_DOCTYPE}` set declaration_cloture = NULL
                where declaration_cloture = %(dm)s""",
            {"dm": doc.name},
        )
        frappe.db.set_value(DM_DOCTYPE, doc.name, "status", STATUS_BROUILLON, update_modified=False)
        _write_back_mensuelle(doc.name, doc.mensuelle, STATUS_BROUILLON)
        return {"name": doc.name, "status": STATUS_BROUILLON}
    except ValueError as error:
        _throw(str(error))


@frappe.whitelist(methods=["POST"])
def depose_declaration(name: str, numero_recepisse: str, date_depot: str = "") -> dict:
    """Depot: Cloture -> Depose, irreversible, Accounts Manager (+ System
    Manager) only."""
    frappe = _frappe()
    try:
        roles = set(frappe.get_roles())
        if not (roles & {"Accounts Manager", "System Manager"}):
            from frappe import _

            frappe.throw(_("Le depot est reserve aux Accounts Manager."), frappe.PermissionError)

        doc = _require_dm(name)
        if doc.status != STATUS_CLOTURE:
            raise ValueError(f"La declaration {name} est {doc.status}: seule une Cloture peut etre deposee.")
        if not (numero_recepisse or "").strip():
            raise ValueError("Le numero de recepisse est obligatoire au depot.")

        frappe.db.set_value(
            DM_DOCTYPE,
            doc.name,
            {
                "status": STATUS_DEPOSE,
                "numero_recepisse": numero_recepisse.strip(),
                "depose_le": date_depot or frappe.utils.now_datetime(),
            },
            update_modified=False,
        )
        _write_back_mensuelle(doc.name, doc.mensuelle, STATUS_DEPOSE)
        return {"name": doc.name, "status": STATUS_DEPOSE}
    except ValueError as error:
        _throw(str(error))


@frappe.whitelist(methods=["POST"])
def get_rubrique_ledger(name: str, code: str) -> dict:
    """The ledger rows behind one rubrique line (the drill-down dialog)."""
    frappe = _frappe()
    try:
        doc = _require_dm(name)
        line = next((l for l in (doc.rubriques or []) if l.code == code), None)
        if not line:
            raise ValueError(f"La rubrique {code} n'existe pas dans {name}.")
        row_names = [x.strip() for x in (line.ecritures or "").split(",") if x.strip()]
        if not row_names:
            return {"code": code, "rows": [], "total_debit": 0.0, "total_credit": 0.0}
        rows = frappe.get_all(
            LEDGER_DOCTYPE,
            filters=[["name", "in", row_names]],
            fields=[
                "name",
                "posting_date",
                "journal",
                "mvt",
                "account",
                "libelle",
                "debit",
                "credit",
                "source_entry_doctype",
                "source_entry",
            ],
            order_by="posting_date asc, name asc",
        )
        return {
            "code": code,
            "rows": rows,
            "total_debit": rate3(sum(float(r.debit or 0) for r in rows)),
            "total_credit": rate3(sum(float(r.credit or 0) for r in rows)),
        }
    except ValueError as error:
        _throw(str(error))
