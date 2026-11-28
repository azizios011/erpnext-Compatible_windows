# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Rapprochement bancaire — the frappe-free core.

Two consumers ride on this module:
- the routed read reports "Bank Reconciliation Statement" (the balance
  view) and "Bank Clearance Summary" (the line view), served from
  custom_modules/bank_reconciliation/report/… through the Module Def
  re-point (no core edit under erpnext/accounts/);
- the Rapprochement Manuel page, whose read endpoint is
  rapprochement_api.lignes.

The write side (rapprocher / de_rapprocher / set_solde_initial) lives in
rapprochement_api.py. Rows are plain dicts mirroring the Ecriture Comptable
ledger fields this logic needs:

    posting_date (date), debit, credit (float),
    rapprochement_manuel (0/1), date_rapprochement (date | None),
    journal, account, tresorerie, ref_doc, libelle, mvt, …

Semantics
---------
A row is RAPPROCHEE at a date `as_of` when it was marked
(rapprochement_manuel) and its date_rapprochement is set and not after
`as_of` — mirroring erpnext's clearance_date test in
Bank Reconciliation Statement (clearance_date.isnull() | clearance_date >
report_date). A row marked with a later date is NOT yet cleared at `as_of`.

The statement follows erpnext's layout and math:
    solde_comptable            = sum(debit - credit) up to the date
    cheques emis non rapproches  = sum(credit) of non-rapprochees
    encaissements non rapproches = sum(debit)  of non-rapprochees
    solde_releve_theorique     = solde_comptable - encaissements + cheques
(a cheque issued and not yet presented is a book credit the releve does
not show yet — the releve balance is HIGHER than the books; an
encaissement booked but not yet on the releve makes it LOWER).

All amounts round to 3 decimals (TND millimes).
"""

from datetime import date

ROUND = 3


def r3(value) -> float:
    return round(float(value or 0.0), ROUND)


def is_rapprochee(row: dict, as_of=None) -> bool:
    """Cleared at `as_of`: marked AND dated, the date not after as_of.
    as_of=None means 'now' (no date window)."""
    if not row.get("rapprochement_manuel"):
        return False
    cleared_on = row.get("date_rapprochement")
    if not cleared_on:
        return False
    if as_of is not None and _as_date(cleared_on) > _as_date(as_of):
        return False
    return True


def _in_date_range(row: dict, from_date=None, to_date=None) -> bool:
    posting = row.get("posting_date")
    if posting is None:
        return True
    posting = _as_date(posting)
    if from_date is not None and posting < _as_date(from_date):
        return False
    if to_date is not None and posting > _as_date(to_date):
        return False
    return True


def _as_date(value):
    if value is None or hasattr(value, "year"):
        return value
    return date.fromisoformat(str(value))


def filter_line_rows(rows: list[dict], filters: dict | None = None) -> list[dict]:
    """The line view (Bank Clearance Summary / Rapprochement Manuel page):
    type_ecriture (Toutes / Rapprochees / Non rapprochees), journal, account,
    from_date/to_date on posting_date, piece de tresorerie, and the exact
    date_rapprochement match. Oldest first (the reconciliation reads like the
    releve)."""
    filters = filters or {}
    out = []
    type_ecriture = filters.get("type_ecriture") or "Toutes"
    for row in rows:
        if type_ecriture == "Rapprochees" and not is_rapprochee(row):
            continue
        if type_ecriture == "Non rapprochees" and is_rapprochee(row):
            continue
        if filters.get("journal") and row.get("journal") != filters["journal"]:
            continue
        if filters.get("account") and row.get("account") != filters["account"]:
            continue
        if filters.get("tresorerie") and row.get("tresorerie") != filters["tresorerie"]:
            continue
        if filters.get("date_rapprochement"):
            cleared_on = _as_date(row.get("date_rapprochement")) if row.get("date_rapprochement") else None
            if cleared_on != _as_date(filters["date_rapprochement"]):
                continue
        if not _in_date_range(row, filters.get("from_date"), filters.get("to_date")):
            continue
        out.append(row)

    return sorted(out, key=lambda r: (str(r.get("posting_date") or ""), str(r.get("creation") or "")))


def totals(rows: list[dict]) -> dict:
    """Total Debit / Credit / Solde over the given rows (3 decimals)."""
    total_debit = r3(sum(r3(r.get("debit")) for r in rows))
    total_credit = r3(sum(r3(r.get("credit")) for r in rows))
    return {
        "total_debit": total_debit,
        "total_credit": total_credit,
        "solde": r3(total_debit - total_credit),
    }


def compute_statement(rows: list[dict], up_to_date, solde_initial: float | None = None) -> dict:
    """The balance view (Bank Reconciliation Statement).

    `rows` = every ledger row of ONE bank account within the context scope
    (caller filters entreprise/exercice/account); rows after up_to_date may
    be included, they are excluded here. `solde_initial` = the signed
    statement-side opening (Solde Initial Banque, Debit positive / Credit
    negative) — displayed as a reference row, not part of the math.
    """
    up_to = _as_date(up_to_date)
    scoped = [r for r in rows if _in_date_range(r, None, up_to)]

    total_debit = r3(sum(r3(r.get("debit")) for r in scoped))
    total_credit = r3(sum(r3(r.get("credit")) for r in scoped))
    solde_comptable = r3(total_debit - total_credit)

    outstanding = [r for r in scoped if not is_rapprochee(r, as_of=up_to)]
    debit_nr = r3(sum(r3(r.get("debit")) for r in outstanding))
    credit_nr = r3(sum(r3(r.get("credit")) for r in outstanding))
    cheques_emis = credit_nr  # book credits not yet on the releve
    encaissements = debit_nr  # book debits not yet on the releve

    return {
        "solde_comptable": solde_comptable,
        "cheques_emis_non_rapproches": cheques_emis,
        "encaissements_non_rapproches": encaissements,
        "total_debit_non_rapproche": debit_nr,
        "total_credit_non_rapproche": credit_nr,
        "count_non_rapprochees": len(outstanding),
        "count_debit_non_rapprochees": sum(1 for r in outstanding if r3(r.get("debit"))),
        "count_credit_non_rapprochees": sum(1 for r in outstanding if r3(r.get("credit"))),
        "solde_releve_theorique": r3(solde_comptable - debit_nr + credit_nr),
        "count_scoped": len(scoped),
        "count_rapprochees": len(scoped) - len(outstanding),
        "solde_initial": r3(solde_initial) if solde_initial is not None else None,
    }
