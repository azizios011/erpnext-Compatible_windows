"""
erpnext/tunisian_accounting/setup.py

Two responsibilities, both triggered by after_install in erpnext/hooks.py:

  1. build_coa_json()          — writes verified/tn_plan_comptable_avec_code.json
                                 (used by ERPNext when creating a Company)

  2. populate_plan_comptable() — inserts all 403 accounts into the
                                 "Chart of Accounts" DocType so the tree
                                 is populated and usable immediately after install.

  The public entry point build_and_populate() calls both in order.
"""

import json
import os

import frappe

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(_HERE, "data")
MAX_ACCOUNT_NAME = 120

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
# Class 1 split:  10-14 → Equity  |  15-19 → Liability
# Class 4 split:  40    → Liability  |  41-49 → Asset
# ---------------------------------------------------------------------------
TOP_LEVEL_GROUPS = {
    "Capitaux Propres et Réserves":       {"root_type": "Equity",    "code": "CAP"},
    "Provisions et Dettes à Long Terme":  {"root_type": "Liability", "code": "PROV-LT"},
    "Actifs Non Courants":                {"root_type": "Asset",     "code": "ANC"},
    "Stocks":                             {"root_type": "Asset",     "code": "STOCKS"},
    "Créances et Actifs Courants":        {"root_type": "Asset",     "code": "CAC"},
    "Dettes Courantes":                   {"root_type": "Liability", "code": "DC"},
    "Trésorerie":                         {"root_type": "Asset",     "code": "TRESO"},
    "Charges":                            {"root_type": "Expense",   "code": "CHARG"},
    "Produits":                           {"root_type": "Income",    "code": "PROD"},
}


def _get_top_level_group(code):
    p2 = code[:2]
    if p2 in ("10", "11", "12", "13", "14"):
        return "Capitaux Propres et Réserves"
    if p2 in ("15", "16", "17", "18", "19"):
        return "Provisions et Dettes à Long Terme"
    if code.startswith("2"):
        return "Actifs Non Courants"
    if code.startswith("3"):
        return "Stocks"
    if p2 == "40":
        return "Dettes Courantes"
    if code.startswith("4"):
        return "Créances et Actifs Courants"
    if code.startswith("5"):
        return "Trésorerie"
    if code.startswith("6"):
        return "Charges"
    if code.startswith("7"):
        return "Produits"
    return None


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


def _truncate_account_name(value, max_length=MAX_ACCOUNT_NAME):
    return (value or "")[:max_length]


def _make_unique_account_key(libelle, code, used_keys):
    base = _truncate_account_name(libelle)
    key = base
    if key in used_keys:
        suffix = f" ({code})"
        key = f"{base[: MAX_ACCOUNT_NAME - len(suffix)]}{suffix}"
    used_keys.add(key)
    return key


def _get_account_type(code):
    p3 = code[:3]
    p2 = code[:2]
    by_3 = {
        "411": "Receivable", "413": "Receivable", "416": "Receivable",
        "401": "Payable",    "403": "Payable",
        "521": "Bank",       "522": "Bank",       "523": "Bank",
        "681": "Depreciation", "682": "Depreciation",
    }
    if p3 in by_3:
        return by_3[p3]
    return {"53": "Cash", "44": "Tax"}.get(p2)


# ---------------------------------------------------------------------------
# Shared: load flat account list from data/
# ---------------------------------------------------------------------------
def _load_all_accounts():
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
# 1. build_coa_json — generates the verified/ JSON template
# ---------------------------------------------------------------------------
def _build_tree(all_accounts):
    buckets = {g: {} for g in TOP_LEVEL_GROUPS}
    for acc in all_accounts:
        code  = acc["code"]
        group = _get_top_level_group(code)
        if not group:
            continue
        buckets[group].setdefault(code[:2], []).append(acc)

    tree = {}
    for group_name, meta in TOP_LEVEL_GROUPS.items():
        postes = buckets.get(group_name, {})
        if not postes:
            continue
        group_node = {"root_type": meta["root_type"], "is_group": 1}
        for p2 in sorted(postes.keys()):
            accs = sorted(postes[p2], key=lambda x: x["code"])
            poste_label = POSTE_LABELS.get(p2, f"Comptes {p2}")
            poste_node  = {"account_number": p2, "is_group": 1}
            used_keys   = set()
            for acc in accs:
                code    = acc["code"]
                libelle = _truncate_account_name(acc["libelle"])
                key     = _make_unique_account_key(libelle, code, used_keys)
                leaf    = {"account_number": code}
                atype   = _get_account_type(code)
                if atype:
                    leaf["account_type"] = atype
                poste_node[key] = leaf
            group_node[poste_label] = poste_node
        tree[group_name] = group_node
    return tree


def build_coa_json():
    """Generate tn_plan_comptable_avec_code.json from tunisian_accounting/data/."""
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
    print(f"[tunisian_accounting] COA JSON written → {OUTPUT_FILE}")


# ---------------------------------------------------------------------------
# 2. populate_plan_comptable — inserts records into Chart of Accounts DocType
# ---------------------------------------------------------------------------
def populate_plan_comptable():
    """
    Inserts all accounts from data/ into the 'Chart of Accounts' DocType.

    Three-level tree:
        Root groups   (short code like 'CAP', no parent)
        Poste groups  (code 'P-10', parent = root group code)
        Leaf accounts (6-digit code, parent = poste group code)
    """
    print("[tunisian_accounting] Populating Chart of Accounts DocType …")

    # Idempotent — skip if already done
    if frappe.db.count("Chart of Accounts") > 0:
        print("[tunisian_accounting] Chart of Accounts already populated — skipping.")
        return

    all_accounts = _load_all_accounts()
    if not all_accounts:
        print("[tunisian_accounting] ERROR: No accounts loaded — aborting populate.")
        return

    # Bucket: group_name → poste(2-digit) → [account dicts]
    buckets = {g: {} for g in TOP_LEVEL_GROUPS}
    for acc in all_accounts:
        code  = acc["code"]
        group = _get_top_level_group(code)
        if not group:
            continue
        buckets[group].setdefault(code[:2], []).append(acc)

    inserted = 0

    def _insert(name, account_name, account_number, is_group,
                 root_type="", account_type="", sens="", parent=""):
        nonlocal inserted
        if frappe.db.exists("Chart of Accounts", name):
            return
        doc = frappe.new_doc("Chart of Accounts")
        doc.name                     = name
        doc.account_name             = account_name
        doc.account_number           = account_number
        doc.is_group                 = is_group
        doc.root_type                = root_type
        doc.account_type             = account_type
        doc.sens                     = sens
        doc.parent_chart_of_accounts = parent
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory   = True
        doc.insert()
        inserted += 1

    # Step 1 — root groups
    for group_name, meta in TOP_LEVEL_GROUPS.items():
        _insert(
            name         = meta["code"],
            account_name = group_name,
            account_number = meta["code"],
            is_group     = 1,
            root_type    = meta["root_type"],
        )

    # Step 2 — poste groups
    created_postes = set()
    for group_name, meta in TOP_LEVEL_GROUPS.items():
        for p2 in sorted(buckets.get(group_name, {}).keys()):
            poste_key = f"P-{p2}"
            if poste_key in created_postes:
                continue
            created_postes.add(poste_key)
            _insert(
                name           = poste_key,
                account_name   = POSTE_LABELS.get(p2, f"Comptes {p2}"),
                account_number = poste_key,
                is_group       = 1,
                root_type      = meta["root_type"],
                parent         = meta["code"],
            )

    # Step 3 — leaf accounts
    for group_name, meta in TOP_LEVEL_GROUPS.items():
        for p2, accs in sorted(buckets.get(group_name, {}).items()):
            poste_key  = f"P-{p2}"
            used_codes = set()
            for acc in sorted(accs, key=lambda x: x["code"]):
                code    = acc["code"]
                libelle = _truncate_account_name(acc["libelle"])
                sens    = acc.get("sens", "")
                atype   = _get_account_type(code)

                leaf_name = code if code not in used_codes else f"{code}-B"
                used_codes.add(leaf_name)

                _insert(
                    name           = leaf_name,
                    account_name   = libelle,
                    account_number = code,
                    is_group       = 0,
                    root_type      = meta["root_type"],
                    account_type   = atype or "",
                    sens           = sens,
                    parent         = poste_key,
                )

    frappe.db.commit()
    print(f"[tunisian_accounting] Done — {inserted} Chart of Accounts records inserted.")


# ---------------------------------------------------------------------------
# Public entry point — referenced in erpnext/hooks.py after_install
# ---------------------------------------------------------------------------
def build_and_populate():
    """Run both steps: generate COA JSON template, then populate the DocType."""
    build_coa_json()
    populate_plan_comptable()

