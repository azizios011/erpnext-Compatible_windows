# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Pure, frappe-free core of the imported-entries materialization
(imported_entries.py). Everything here is unit-testable without a site:
grouping, classification and the entry payloads. The frappe I/O (queries,
bulk inserts, linking, jobs) lives in imported_entries.py.

The auxiliary prefixes are defined HERE (single source of truth) and
re-exported by report_common so the reports keep importing them from there.
"""

from datetime import date

AUX_CLIENT_PREFIX = "411"
AUX_FOURNISSEUR_PREFIX = "401"

PAYABLE_DOCTYPE = "Payable Transaction"
RECEIVABLE_DOCTYPE = "Receivable Transaction"
TREASURY_DOCTYPE = "Treasury Transaction"
ALL_ENTRY_DOCTYPES = (PAYABLE_DOCTYPE, RECEIVABLE_DOCTYPE, TREASURY_DOCTYPE)

# journal_type → the doctype that wins a mixed (supplier + client) group:
# purchase journals → Payable, sales journals → Receivable; the neutral
# journals (Banque, Declaration, Operations Diverses) leave a mixed group
# unclassified on purpose (never a guessed third doctype)
JOURNAL_TYPE_TO_ENTRY = {
	"Achat": PAYABLE_DOCTYPE,
	"Retenue": PAYABLE_DOCTYPE,
	"Vente": RECEIVABLE_DOCTYPE,
}


def is_supplier_line(account_number: str) -> bool:
	return bool(account_number) and account_number.startswith(AUX_FOURNISSEUR_PREFIX)


def is_client_line(account_number: str) -> bool:
	return bool(account_number) and account_number.startswith(AUX_CLIENT_PREFIX)


def group_imported_rows(rows: list) -> dict[tuple[str, str], list]:
	"""Group imported ledger rows per movement: same (journal, mvt). The
	dock context (entreprise + exercice) is fixed upstream. Returns the
	groups keyed (journal, mvt), preserving first-seen order."""
	groups: dict[tuple[str, str], list] = {}
	for row in rows:
		key = (row["journal"] or "", row["mvt"] or "")
		groups.setdefault(key, []).append(row)
	return groups


def classify_group(journal_type: str | None, lines: list[dict]) -> str:
	"""The entry doctype for a group of imported lines. lines carry account_number.
	Both sign directions classify the same way. Aux-prefix rule first:
	401 -> Payable Transaction, 411 -> Receivable Transaction.
	A group with both is decided by the journal's type (purchase -> Payable, sales -> Receivable).
	Everything else (bank, cash, OD, opening balances, declaration journals,
	mixed groups under neutral journals) -> Treasury Transaction."""
	has_supplier = any(is_supplier_line(line["account_number"]) for line in lines)
	has_client = any(is_client_line(line["account_number"]) for line in lines)
	if has_supplier and not has_client:
		return PAYABLE_DOCTYPE
	if has_client and not has_supplier:
		return RECEIVABLE_DOCTYPE
	if has_supplier and has_client:
		resolved = JOURNAL_TYPE_TO_ENTRY.get(journal_type or "")
		if resolved:
			return resolved
	return TREASURY_DOCTYPE


def _round3(value) -> float:
	return round(float(value or 0), 3)


def build_entry_payload(
	entry_doctype: str,
	journal: str,
	mvt: str,
	posting_date: date,
	import_batch: str,
	rows: list[dict],
) -> tuple[dict, list[dict]]:
	"""(parent dict, child line dicts) for one imported movement — the shape
	the bulk inserts write. Lines keep account, libelle, ref, debit, credit
	and tresorerie exactly as imported; the parent mirrors what
	EntryDocument.compute_totals / derive_period would compute."""
	rows = [row for row in rows]
	total_debit = _round3(sum(_round3(row["debit"]) for row in rows))
	total_credit = _round3(sum(_round3(row["credit"]) for row in rows))
	ref_doc = next((row["ref_doc"] for row in rows if row.get("ref_doc")), "")
	posting_date = posting_date if isinstance(posting_date, date) else None
	parent = {
		"doctype": entry_doctype,
		"name": mvt,
		"date_operation": posting_date,
		"journal": journal,
		"mois": f"{posting_date.month:02d}" if posting_date else "",
		"jour": posting_date.day if posting_date else 0,
		"devise": "TND",
		"mvt": mvt,
		"ref_doc": ref_doc or mvt,
		"libelle": "",
		"source_doctype": "",
		"source_name": "",
		"entreprise": rows[0]["entreprise"],
		"exercice": rows[0]["exercice"],
		"total_debit": total_debit,
		"total_credit": total_credit,
		"solde": round(total_debit - total_credit, 3),
		"status": "Comptabilise",
		"imported": 1,
		"import_batch": import_batch,
	}
	lines = [
		{
			"account": row["account"],
			"libelle": row["libelle"],
			"fact": "",
			"tresorerie": row.get("tresorerie") or "",
			"debit": _round3(row["debit"]),
			"credit": _round3(row["credit"]),
			"idx": index,
		}
		for index, row in enumerate(rows, start=1)
	]
	return parent, lines


def materialize_plan(
	rows: list[dict],
	journal_types: dict[str, str],
	account_numbers: dict[str, str],
	split_multiref: bool = False,
) -> dict:
	"""The classification plan over the unlinked imported rows: which
	groups become which entry doctype (Payable, Receivable, Treasury),
	with multi-ref/date detection, per-journal counts, and optional splitting."""
	plan: dict[str | None, list] = {
		PAYABLE_DOCTYPE: [],
		RECEIVABLE_DOCTYPE: [],
		TREASURY_DOCTYPE: [],
		None: [],
	}
	per_journal: dict[str, dict[str, int]] = {}
	groups_with_multiple_refs_or_dates: list[tuple[str, str]] = []
	unbalanced_groups: list[dict] = []
	unresolvable_groups: list[dict] = []

	for (journal, mvt), group_rows in group_imported_rows(rows).items():
		distinct_dates = {r.get("posting_date") for r in group_rows if r.get("posting_date")}
		distinct_refs = {r.get("ref_doc") for r in group_rows if r.get("ref_doc")}
		has_multi = len(distinct_dates) > 1 or len(distinct_refs) > 1
		if has_multi:
			groups_with_multiple_refs_or_dates.append((journal, mvt))

		tot_debit = _round3(sum(_round3(r.get("debit")) for r in group_rows))
		tot_credit = _round3(sum(_round3(r.get("credit")) for r in group_rows))
		is_unbalanced = abs(tot_debit - tot_credit) > 0.001
		if is_unbalanced:
			unbalanced_groups.append({
				"journal": journal,
				"mvt": mvt,
				"debit": tot_debit,
				"credit": tot_credit,
			})

		if split_multiref and (has_multi or is_unbalanced):
			# Split by (ref_doc, posting_date)
			subgroups: dict[tuple, list] = {}
			for r in group_rows:
				skey = (r.get("ref_doc") or "", r.get("posting_date"))
				subgroups.setdefault(skey, []).append(r)

			all_balanced = all(
				abs(
					_round3(sum(_round3(sr.get("debit")) for sr in srows))
					- _round3(sum(_round3(sr.get("credit")) for sr in srows))
				)
				<= 0.001
				for srows in subgroups.values()
			)

			if all_balanced and len(subgroups) > 1:
				for sidx, (_skey, srows) in enumerate(subgroups.items(), start=1):
					entry_name = f"{mvt}-{sidx}"
					lines = [
						{
							"account_number": account_numbers.get(row["account"], ""),
							"debit": row["debit"],
							"credit": row["credit"],
						}
						for row in srows
					]
					entry_doctype = classify_group(journal_types.get(journal), lines)
					plan[entry_doctype].append((journal, entry_name, srows))
					stats = per_journal.setdefault(
						journal,
						{
							PAYABLE_DOCTYPE: 0,
							RECEIVABLE_DOCTYPE: 0,
							TREASURY_DOCTYPE: 0,
							"unclassified": 0,
						},
					)
					if entry_doctype:
						stats[entry_doctype] += 1
					else:
						stats["unclassified"] += 1
				continue
			else:
				if is_unbalanced:
					unresolvable_groups.append({
						"journal": journal,
						"mvt": mvt,
						"debit": tot_debit,
						"credit": tot_credit,
					})

		lines = [
			{
				"account_number": account_numbers.get(row["account"], ""),
				"debit": row["debit"],
				"credit": row["credit"],
			}
			for row in group_rows
		]
		entry_doctype = classify_group(journal_types.get(journal), lines)
		plan[entry_doctype].append((journal, mvt, group_rows))
		stats = per_journal.setdefault(
			journal,
			{
				PAYABLE_DOCTYPE: 0,
				RECEIVABLE_DOCTYPE: 0,
				TREASURY_DOCTYPE: 0,
				"unclassified": 0,
			},
		)
		if entry_doctype:
			stats[entry_doctype] += 1
		else:
			stats["unclassified"] += 1

	return {
		"plan": plan,
		"per_journal": per_journal,
		"groups_with_multiple_refs_or_dates": groups_with_multiple_refs_or_dates,
		"unbalanced_groups": unbalanced_groups,
		"unresolvable_groups": unresolvable_groups,
	}
