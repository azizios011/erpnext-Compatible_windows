"""
erpnext/tunisian_accounting/setup.py

Generates  erpnext/accounts/doctype/account/chart_of_accounts/verified/
           tn_plan_comptable_avec_code.json

from the flat per-class JSON files in  erpnext/tunisian_accounting/data/

Called automatically by Frappe via the after_install hook defined in
erpnext/tunisian_accounting/hooks.py
"""

import json
import os

# ---------------------------------------------------------------------------
# Paths (relative to this file's location inside tunisian_accounting/)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(_HERE, "data")

OUTPUT_FILE = os.path.normpath(
    os.path.join(
        _HERE,
        "..", "accounts", "doctype", "account",
        "chart_of_accounts", "verified",
        "tn_plan_comptable_avec_code.json",
    )
)

# ---------------------------------------------------------------------------
# Top-level tree groups
# Each group sets the root_type inherited by ALL its children in ERPNext.
#
# Class 1 is split:
#   codes 10-14  →  Equity   (capital, réserves, résultats)
#   codes 15-19  →  Liability (provisions, emprunts)
#
# Class 4 is split:
#   code  40     →  Liability (fournisseurs)
#   codes 41-49  →  Asset     (clients, personnel, état…)
# ---------------------------------------------------------------------------
TOP_LEVEL_GROUPS = {
    "Capitaux Propres et Réserves":       {"root_type": "Equity"},
    "Provisions et Dettes à Long Terme":  {"root_type": "Liability"},
    "Actifs Non Courants":                {"root_type": "Asset"},
    "Stocks":                             {"root_type": "Asset"},
    "Créances et Actifs Courants":        {"root_type": "Asset"},
    "Dettes Courantes":                   {"root_type": "Liability"},
    "Trésorerie":                         {"root_type": "Asset"},
    "Charges":                            {"root_type": "Expense"},
    "Produits":                           {"root_type": "Income"},
}

# ---------------------------------------------------------------------------
# Routing: given a 6-digit account code, return the top-level group name
# ---------------------------------------------------------------------------
def _get_top_level_group(code):
    p2 = code[:2]

    # Class 1
    if p2 in ("10", "11", "12", "13", "14"):
        return "Capitaux Propres et Réserves"
    if p2 in ("15", "16", "17", "18", "19"):
        return "Provisions et Dettes à Long Terme"

    # Class 2
    if code.startswith("2"):
        return "Actifs Non Courants"

    # Class 3
    if code.startswith("3"):
        return "Stocks"

    # Class 4 — fournisseurs separate from clients/état/personnel
    if p2 == "40":
        return "Dettes Courantes"
    if code.startswith("4"):
        return "Créances et Actifs Courants"

    # Class 5
    if code.startswith("5"):
        return "Trésorerie"

    # Class 6
    if code.startswith("6"):
        return "Charges"

    # Class 7
    if code.startswith("7"):
        return "Produits"

    return None  # skip unknown codes


# ---------------------------------------------------------------------------
# Human-readable labels for 2-digit poste sub-groups
# ---------------------------------------------------------------------------
POSTE_LABELS = {
    "10": "Capital et Réserves",
    "11": "Réserves Particulières",
    "12": "Résultats Reportés",
    "13": "Résultat de l'Exercice",
    "14": "Fonds Réglementés et Subventions",
    "15": "Provisions pour Risques et Charges",
    "16": "Emprunts et Dettes Assimilées",
    "17": "Comptes de Liaison",
    "18": "Autres Comptes de Capitaux",
    "19": "Autres Passifs à Long Terme",
    "21": "Immobilisations Incorporelles",
    "22": "Immobilisations Corporelles",
    "23": "Immobilisations en Cours",
    "24": "Avances sur Immobilisations",
    "25": "Participations Groupe",
    "26": "Autres Participations",
    "27": "Autres Immobilisations Financières",
    "28": "Amortissements des Immobilisations",
    "29": "Provisions pour Dépréciation des Immobilisations",
    "30": "Marchandises",
    "31": "Matières Premières et Fournitures",
    "32": "Autres Approvisionnements",
    "33": "En-cours de Production de Biens",
    "34": "En-cours de Production de Services",
    "35": "Stocks de Produits Finis",
    "36": "Stocks à l'Extérieur",
    "37": "Stocks en Cours de Route",
    "38": "Stocks en Consignation",
    "39": "Provisions pour Dépréciation des Stocks",
    "40": "Fournisseurs et Comptes Rattachés",
    "41": "Clients et Comptes Rattachés",
    "42": "Personnel et Comptes Rattachés",
    "43": "Organismes Sociaux",
    "44": "État et Collectivités Publiques",
    "45": "Groupe et Associés",
    "46": "Débiteurs et Créditeurs Divers",
    "47": "Comptes de Régularisation",
    "48": "Autres Comptes de Tiers",
    "49": "Provisions pour Dépréciation des Comptes de Tiers",
    "50": "Valeurs Mobilières de Placement",
    "51": "Opérations Bancaires",
    "52": "Banques et Établissements Financiers",
    "53": "Caisse",
    "54": "Chèques et Valeurs à l'Encaissement",
    "55": "Fonds en Cours de Virement",
    "56": "Valeurs à l'Encaissement",
    "57": "Régies d'Avances",
    "58": "Virements Internes",
    "59": "Provisions pour Dépréciation Financière",
    "60": "Achats de Marchandises et Matières",
    "61": "Services Extérieurs",
    "62": "Autres Services Extérieurs",
    "63": "Impôts, Taxes et Versements Assimilés",
    "64": "Charges de Personnel",
    "65": "Charges Financières",
    "66": "Pertes et Charges Exceptionnelles",
    "67": "Autres Charges",
    "68": "Dotations aux Amortissements et Provisions",
    "69": "Impôts sur les Bénéfices",
    "70": "Ventes de Produits",
    "71": "Production Stockée",
    "72": "Production Immobilisée",
    "73": "Produits Divers Ordinaires",
    "74": "Subventions d'Exploitation",
    "75": "Produits Financiers",
    "76": "Gains Exceptionnels",
    "77": "Gains Extraordinaires",
    "78": "Reprises sur Amortissements et Provisions",
    "79": "Transferts de Charges",
}

# ---------------------------------------------------------------------------
# account_type hints — ERPNext uses these for special journal behaviour
# (Receivable, Payable, Bank, Cash, Tax, Depreciation, etc.)
# ---------------------------------------------------------------------------
def _get_account_type(code):
    p3 = code[:3]
    p2 = code[:2]

    by_prefix3 = {
        "411": "Receivable",
        "413": "Receivable",
        "416": "Receivable",
        "401": "Payable",
        "403": "Payable",
        "521": "Bank",
        "522": "Bank",
        "523": "Bank",
        "681": "Depreciation",
        "682": "Depreciation",
    }
    if p3 in by_prefix3:
        return by_prefix3[p3]

    by_prefix2 = {
        "53": "Cash",
        "44": "Tax",
    }
    return by_prefix2.get(p2)


# ---------------------------------------------------------------------------
# Step 1 — load all class files
# ---------------------------------------------------------------------------
def _load_all_accounts():
    """Read class1..class7 JSON files and return one flat list of accounts."""
    all_accounts = []
    for n in range(1, 8):
        fpath = os.path.join(DATA_DIR, f"class{n}_accounts.json")
        if not os.path.exists(fpath):
            print(f"[tunisian_accounting] WARNING: {fpath} not found — skipping class {n}")
            continue
        with open(fpath, encoding="utf-8") as f:
            data = json.load(f)
        accounts = data["plan_comptable"]["accounts"]
        all_accounts.extend(accounts)
        print(f"[tunisian_accounting] Loaded class {n}: {len(accounts)} accounts")
    return all_accounts


# ---------------------------------------------------------------------------
# Step 2 — build the nested ERPNext tree
# ---------------------------------------------------------------------------
def _build_tree(all_accounts):
    """
    Converts the flat account list into ERPNext's nested COA tree format:

        {
          "Top Level Group": {
            "root_type": "Asset",
            "is_group": 1,
            "Poste Label": {
              "account_number": "41",
              "is_group": 1,
              "Account Name": {
                "account_number": "411000",
                "account_type": "Receivable"   # optional
              },
              ...
            },
            ...
          },
          ...
        }
    """
    # Bucket: group_name → poste (2-digit) → [account, ...]
    buckets = {g: {} for g in TOP_LEVEL_GROUPS}

    for acc in all_accounts:
        code = acc["code"]
        group = _get_top_level_group(code)
        if group is None:
            continue
        p2 = code[:2]
        buckets[group].setdefault(p2, []).append(acc)

    # Assemble
    tree = {}

    for group_name, meta in TOP_LEVEL_GROUPS.items():
        postes = buckets.get(group_name, {})
        if not postes:
            continue

        group_node = {"root_type": meta["root_type"], "is_group": 1}

        for p2 in sorted(postes.keys()):
            accs = sorted(postes[p2], key=lambda x: x["code"])
            poste_label = POSTE_LABELS.get(p2, f"Comptes {p2}")
            poste_node = {"account_number": p2, "is_group": 1}
            used_keys = set()

            for acc in accs:
                code    = acc["code"]
                libelle = acc["libelle"]

                # Guarantee unique key within this poste node
                # (some libelles repeat across different codes, e.g. class 7 reprises)
                key = libelle
                if key in used_keys:
                    key = f"{libelle} ({code})"
                used_keys.add(key)

                leaf = {"account_number": code}
                atype = _get_account_type(code)
                if atype:
                    leaf["account_type"] = atype

                poste_node[key] = leaf

            group_node[poste_label] = poste_node

        tree[group_name] = group_node

    return tree


# ---------------------------------------------------------------------------
# Public entry point — wired to after_install in hooks.py
# ---------------------------------------------------------------------------
def build_coa_json():
    """
    Generate tn_plan_comptable_avec_code.json from tunisian_accounting/data/.

    This function is pure Python (no frappe dependency) so it runs safely
    at any point — during install, in a standalone script, or in tests.
    """
    print("[tunisian_accounting] Building Tunisian COA JSON …")

    all_accounts = _load_all_accounts()
    if not all_accounts:
        print("[tunisian_accounting] ERROR: No accounts loaded — aborting.")
        return

    tree = _build_tree(all_accounts)

    output = {
        "name": "Plan Comptable des Entreprises - Tunisie (avec codes)",
        "disabled": "No",
        "tree": tree,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(
        len(postes)
        for group in tree.values()
        for key, postes in group.items()
        if isinstance(postes, dict) and key not in ("root_type", "is_group")
    )
    print(f"[tunisian_accounting] Done — {len(all_accounts)} accounts written to:")
    print(f"    {OUTPUT_FILE}")
