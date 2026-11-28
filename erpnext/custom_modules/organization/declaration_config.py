# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The standard Déclaration Mensuelle configuration (the 11 Tunisian tax
familles and Axeane's CPR account mapping) as seed data for the
Famille Declaration / Rubrique Declaration doctypes.

The account numbers are Axeane's CPR mapping: DEFAULTS ONLY, meant to be
adjusted per Entreprise after loading. seed_declaration_config (whitelisted,
POST, the config forms' "Charger le modèle standard" button) creates what is
missing and never overwrites an existing record — the accountant's own
adjustments stay. Intervals whose boundary account is missing from the
entreprise's chart are skipped and reported.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from erpnext.custom_modules.organization.context import require_context

FAMILLE_DOCTYPE = "Famille Declaration"
RUBRIQUE_DOCTYPE = "Rubrique Declaration"
COMPTE_DOCTYPE = "Rubrique Declaration Compte"
CHART_DOCTYPE = "Chart of Account"

DEFAULT_EXCLUSION_REASON = _(
    "Famille non applicable au régime de l'entreprise (défaut du modèle standard, modifiable)"
)

# The 11 Tunisian tax familles, in declaration order. inclus: 1 for 1, 2, 3,
# 5, 7, 9 — the others ship excluded (CPR's regime) with a modifiable reason.
SEED_FAMILLES: list[dict] = [
    {"code": 1, "famille_code": "Retenue_A_La_Source", "libelle": "Retenue à la source", "inclus": 1},
    {"code": 2, "famille_code": "TFP", "libelle": "Taxe de formation professionnelle", "inclus": 1},
    {"code": 3, "famille_code": "FOPROLOS", "libelle": "Fonds de promotion du logement", "inclus": 1},
    {"code": 4, "famille_code": "DC", "libelle": "Droit de consommation", "inclus": 0},
    {"code": 5, "famille_code": "TVA", "libelle": "Taxe sur la valeur ajoutée", "inclus": 1},
    {"code": 6, "famille_code": "Autres_taxes_sur_CA", "libelle": "Autres taxes sur chiffre d'affaires", "inclus": 0},
    {"code": 7, "famille_code": "Droit_de_timbre", "libelle": "Droit de timbre fiscal", "inclus": 1},
    {"code": 8, "famille_code": "Taxe_hoteliere", "libelle": "Taxe hôtelière", "inclus": 0},
    {"code": 9, "famille_code": "TCL", "libelle": "Taxe sur les collectivités locales", "inclus": 1},
    {"code": 10, "famille_code": "Droit_de_licence", "libelle": "Droit de licence", "inclus": 0},
    {"code": 11, "famille_code": "Autres_Informations", "libelle": "Autres informations", "inclus": 0},
]

# Axeane's CPR account mapping (account numbers; a tuple (de, a) with an
# empty upper bound matches by prefix). Brut/retenu calculation types per
# the Déclaration Mensuelle: COMPTE sums the ledger, RETENU_TAUX derives the
# gross from the withheld tax, BRUT_TAUX applies the rate to the gross and
# FIXE stays 0 (manual). The salary-family taux is variable (scale): 0 here.
SEED_RUBRIQUES: list[dict] = [
    {
        "code": "F1_1", "famille": 1, "libelle": "RS Salaires (régime commun / IRPP)",
        "code_rapport": "Page 1, L01", "taux": 0,
        "type_calcul_brut": "COMPTE", "sens_brut": "DEBIT",
        "comptes_brut": [("640000", ""), ("641000", ""), ("641010", "")],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("432100", ""), ("432101", "")],
    },
    {
        "code": "F1_3", "famille": 1, "libelle": "Contribution Sociale Solidarité (CSS)",
        "code_rapport": "Page 1, L02", "taux": 1,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("432102", ""), ("432110", ""), ("432111", "")],
    },
    {
        "code": "F1_4_1", "famille": 1, "libelle": "RS Loyers et commissions (personnes physiques)",
        "code_rapport": "Page 1, L03", "taux": 10,
        "type_calcul_brut": "COMPTE", "sens_brut": "DEBIT",
        "comptes_brut": [("613000", "")],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("432300", "")],
    },
    {
        "code": "F1_6", "famille": 1, "libelle": "RS Honoraires (personnes morales et réel)",
        "code_rapport": "Page 1, L05", "taux": 3,
        "type_calcul_brut": "COMPTE", "sens_brut": "DEBIT",
        "comptes_brut": [("622000", "")],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("432200", "")],
    },
    {
        "code": "F1_17_1", "famille": 1, "libelle": "RS Fournisseurs (achats >= 1000 DT, taux IS 15%)",
        "code_rapport": "Page 1, L06", "taux": 1,
        "type_calcul_brut": "COMPTE", "sens_brut": "DEBIT",
        "comptes_brut": [("607000", "")],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("432000", "432081"), ("432122", "")],
    },
    {
        "code": "F2_1", "famille": 2, "libelle": "TFP (taux modifiable)",
        "code_rapport": "Page 1", "taux": 2,
        "type_calcul_brut": "COMPTE", "sens_brut": "DEBIT",
        "comptes_brut": [("640000", ""), ("641000", ""), ("641010", "")],
        "type_calcul_retenu": "BRUT_TAUX", "sens_retenu": "",
        "comptes_retenu": [],
    },
    {
        "code": "F3_1", "famille": 3, "libelle": "FOPROLOS",
        "code_rapport": "Page 1", "taux": 1,
        "type_calcul_brut": "COMPTE", "sens_brut": "DEBIT",
        "comptes_brut": [("640000", ""), ("641000", ""), ("641010", "")],
        "type_calcul_retenu": "BRUT_TAUX", "sens_retenu": "",
        "comptes_retenu": [],
    },
    {
        "code": "F5_1_1", "famille": 5, "libelle": "Chiffre d'affaires soumis à TVA 7%",
        "code_rapport": "Page 2, L01", "taux": 7,
        "type_calcul_brut": "RETENU_TAUX", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("436707", "")],
    },
    {
        "code": "F5_1_2", "famille": 5, "libelle": "Chiffre d'affaires soumis à TVA 13%",
        "code_rapport": "Page 2, L02", "taux": 13,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "FIXE", "sens_retenu": "",
        "comptes_retenu": [],
    },
    {
        "code": "F5_1_3", "famille": 5, "libelle": "Chiffre d'affaires soumis à TVA 19%",
        "code_rapport": "Page 2, L03", "taux": 19,
        "type_calcul_brut": "RETENU_TAUX", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("436719", "")],
    },
    {
        "code": "F5_2_1", "famille": 5, "libelle": "TVA déductible - Achats immobiliers",
        "code_rapport": "Page 2, L05", "taux": 0,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "FIXE", "sens_retenu": "",
        "comptes_retenu": [],
    },
    {
        "code": "F5_2_2", "famille": 5, "libelle": "TVA déductible - Équipements locaux",
        "code_rapport": "Page 2, L06", "taux": 0,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "FIXE", "sens_retenu": "",
        "comptes_retenu": [],
    },
    {
        "code": "F5_2_3", "famille": 5, "libelle": "TVA déductible - Équipements importés",
        "code_rapport": "Page 2, L07", "taux": 0,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "FIXE", "sens_retenu": "",
        "comptes_retenu": [],
    },
    {
        "code": "F5_2_4", "famille": 5, "libelle": "TVA déductible - Autres achats locaux",
        "code_rapport": "Page 2, L08", "taux": 0,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "DEBIT",
        "comptes_retenu": [("436600", ""), ("436607", ""), ("436613", ""), ("436660", "")],
    },
    {
        "code": "F5_2_5", "famille": 5, "libelle": "TVA déductible - Autres achats importés",
        "code_rapport": "Page 2, L09", "taux": 0,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "FIXE", "sens_retenu": "",
        "comptes_retenu": [],
    },
    {
        "code": "F5_3_1", "famille": 5, "libelle": "Retenue TVA 25% sur marchés et achats >= 1000 DT",
        "code_rapport": "Page 2, L10", "taux": 25,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("436666", "")],
    },
    {
        "code": "F7", "famille": 7, "libelle": "Droit de timbre (1.000 DT par pièce)",
        "code_rapport": "Page 3, L01", "taux": 1,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("437000", "")],
    },
    {
        "code": "F9_3_1", "famille": 9, "libelle": "TCL chiffre d'affaires brut local",
        "code_rapport": "Page 3, L02", "taux": 0.2,
        "type_calcul_brut": "COMPTE", "sens_brut": "CREDIT",
        "comptes_brut": [("707007", ""), ("707019", "")],
        "type_calcul_retenu": "COMPTE", "sens_retenu": "CREDIT",
        "comptes_retenu": [("436000", ""), ("436520", "")],
    },
    {
        "code": "F9_3_2", "famille": 9, "libelle": "TCL CA export (totalement exportatrice)",
        "code_rapport": "Page 3, L03", "taux": 0.1,
        "type_calcul_brut": "FIXE", "sens_brut": "",
        "comptes_brut": [],
        "type_calcul_retenu": "BRUT_TAUX", "sens_retenu": "",
        "comptes_retenu": [],
    },
]


def _chart_numbers(entreprise: str) -> dict[str, str]:
    """account_number -> Chart of Account name, for the entreprise's chart."""
    rows = frappe.get_all(
        CHART_DOCTYPE,
        filters={"entreprise": entreprise},
        fields=["name", "account_number"],
    )
    return {(row.account_number or "").strip(): row.name for row in rows if row.account_number}


def _compte_rows(intervals: list, chart: dict[str, str], missing: list[str]) -> list[dict]:
    """Interval tuples (number, upper) as Rubrique Declaration Compte child
    dicts, boundaries resolved to the chart's accounts. An interval whose
    boundary is missing from the chart is skipped and reported."""
    rows: list[dict] = []
    for de, a in intervals:
        de_name = chart.get(de.strip())
        if not de_name:
            missing.append(de.strip())
            continue
        row = {"compte_de": de_name, "compte_a": ""}
        if (a or "").strip():
            a_name = chart.get(a.strip())
            if not a_name:
                missing.append(a.strip())
                continue
            row["compte_a"] = a_name
        rows.append(row)
    return rows


@frappe.whitelist(methods=["POST"])
def seed_declaration_config(entreprise: str = "") -> dict:
    """Charge le modèle standard: create the 11 familles and Axeane's CPR
    rubriques for the context Entreprise. Idempotent — existing records are
    left untouched (the accountant's adjustments stay). Intervals whose
    boundary account is missing from the entreprise's chart are skipped and
    reported in the result."""
    context = require_context()
    if entreprise and entreprise != context["entreprise"]:
        frappe.throw(
            _("L'entreprise {0} n'est pas celle du contexte comptable ({1}).").format(
                entreprise, context["entreprise"]
            )
        )
    entreprise = context["entreprise"]
    chart = _chart_numbers(entreprise)

    familles_created: list[str] = []
    familles_existing = 0
    for seed in SEED_FAMILLES:
        name = f"{entreprise}-F{cint(seed['code'])}"
        if frappe.db.exists(FAMILLE_DOCTYPE, name):
            familles_existing += 1
            continue
        doc = frappe.get_doc(
            {
                "doctype": FAMILLE_DOCTYPE,
                "entreprise": entreprise,
                "code": seed["code"],
                "famille_code": seed["famille_code"],
                "libelle": seed["libelle"],
                "inclus": seed["inclus"],
            }
        )
        if not cint(seed["inclus"]):
            doc.exclusion_reason = DEFAULT_EXCLUSION_REASON
        doc.insert()
        familles_created.append(name)

    missing_accounts: list[str] = []
    rubriques_created: list[str] = []
    rubriques_existing = 0
    for seed in SEED_RUBRIQUES:
        code = seed["code"]
        name = f"{entreprise}-{code}"
        if frappe.db.exists(RUBRIQUE_DOCTYPE, name):
            rubriques_existing += 1
            continue
        famille_name = f"{entreprise}-F{cint(seed['famille'])}"
        if not frappe.db.exists(FAMILLE_DOCTYPE, famille_name):
            frappe.throw(
                _("La famille {0} est absente: chargez d'abord le modèle standard.").format(famille_name)
            )
        doc = frappe.get_doc(
            {
                "doctype": RUBRIQUE_DOCTYPE,
                "entreprise": entreprise,
                "famille": famille_name,
                "code": code,
                "libelle": seed["libelle"],
                "code_rapport": seed["code_rapport"],
                "taux": seed["taux"],
                "actif": 1,
                "type_calcul_brut": seed["type_calcul_brut"],
                "sens_brut": seed["sens_brut"],
                "type_calcul_retenu": seed["type_calcul_retenu"],
                "sens_retenu": seed["sens_retenu"],
            }
        )
        for row in _compte_rows(seed["comptes_brut"], chart, missing_accounts):
            doc.append("comptes_brut", row)
        for row in _compte_rows(seed["comptes_retenu"], chart, missing_accounts):
            doc.append("comptes_retenu", row)
        doc.insert()
        rubriques_created.append(name)

    return {
        "entreprise": entreprise,
        "familles_created": familles_created,
        "familles_existing": familles_existing,
        "rubriques_created": rubriques_created,
        "rubriques_existing": rubriques_existing,
        "missing_accounts": sorted(set(missing_accounts)),
    }
