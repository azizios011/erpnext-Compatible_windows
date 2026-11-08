# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Auto-lettrage rules over the Ecriture Comptable ledger.

Each rule receives the non-lettered lines of ONE account (oldest first) and
returns candidate groups: lists of ledger row dicts that would balance.
Rules never write; the caller letters the sets it accepts.
"""

from frappe.utils import flt

TOLERANCE = 0.001

R1 = "R1"
R2 = "R2"


def run_rules(lines: list[dict], rules: list[str]) -> list[dict]:
	"""Run the requested rules in order; every line joins at most one set."""
	remaining = [line for line in lines if line.get("lettrage_status") == "Non lettre"]
	used: set[str] = set()
	sets: list[dict] = []
	if R1 in rules:
		for candidate in _rule_r1(remaining, used):
			sets.append(candidate)
	if R2 in rules:
		for candidate in _rule_r2(remaining, used):
			sets.append(candidate)
	return sets


def _rule_r1(lines: list[dict], used: set[str]) -> list[dict]:
	"""R1 — same ref_doc whose debits and credits balance."""
	by_ref: dict[str, list[dict]] = {}
	for line in lines:
		ref = (line.get("ref_doc") or "").strip()
		if not ref or line["name"] in used:
			continue
		by_ref.setdefault(ref, []).append(line)

	for ref, group in sorted(by_ref.items()):
		if len(group) < 2:
			continue
		total_debit = flt(sum(flt(line["debit"]) for line in group), 3)
		total_credit = flt(sum(flt(line["credit"]) for line in group), 3)
		if abs(total_debit - total_credit) <= TOLERANCE:
			for line in group:
				used.add(line["name"])
			yield {"rule": R1, "key": ref, "lines": group, "total_debit": total_debit, "total_credit": total_credit}


def _rule_r2(lines: list[dict], used: set[str]) -> list[dict]:
	"""R2 — pairs of equal amounts on opposite sides, oldest first."""
	by_amount: dict[float, dict] = {}
	for line in lines:
		if line["name"] in used:
			continue
		debit, credit = flt(line["debit"]), flt(line["credit"])
		amount = debit if debit > 0 else credit
		if amount <= 0:
			continue
		side = "D" if debit > 0 else "C"
		by_amount.setdefault(amount, {"D": [], "C": []})[side].append(line)

	for amount, sides in sorted(by_amount.items()):
		debits, credits = sides["D"], sides["C"]
		while debits and credits:
			debit_line, credit_line = debits.pop(0), credits.pop(0)
			used.add(debit_line["name"])
			used.add(credit_line["name"])
			yield {
				"rule": R2,
				"key": f"{amount}",
				"lines": [debit_line, credit_line],
				"total_debit": amount,
				"total_credit": amount,
			}
