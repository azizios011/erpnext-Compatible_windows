# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Lettrage — the "Saisie du lettrage" tool over the Ecriture Comptable
ledger (single-doctype tool form, like the Bank Reconciliation Tool).

Everything here is parameterized; ledger rows are only ever touched with
frappe.db.set_value / frappe.db.delete after a Lettrage permission check —
the ledger itself stays read-only for users.
"""

import json
from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from erpnext.custom_modules.reports.doctype.lettrage.lettrage_rules import run_rules

LEDGER = "Ecriture Comptable"
TOLERANCE = 0.001
SUGGEST_LIMIT = 50


class Lettrage(Document):
	"""Single doctype — the UI is rendered into ui_html by
	erpnext/public/js/lettrage.bundle.js."""

	pass

# Tunisian PCG (plan comptable) prefixes per lettrage category. No PCT seed
# data ships in the organization module, so the standard prefixes stand.
CATEGORY_PREFIXES = {
	"Clients": "41",
	"Fournisseurs": "40",
	"Salaries": "42",
	"Debiteurs-Crediteurs": "46",
}
CATEGORIES = ("Tous",) + tuple(CATEGORY_PREFIXES) + ("Autres",)

TREASURY_ACCOUNT_TYPES = ("Bank", "Cash")


from frappe.model.document import Document

# ── permissions ──────────────────────────────────────────────────────────────


def _check_read() -> None:
	if not frappe.has_permission("Lettrage", "read"):
		frappe.throw(_("Not permitted to use the Lettrage tool"), frappe.PermissionError)


def _check_write() -> None:
	if not frappe.has_permission("Lettrage", "write"):
		frappe.throw(_("Not permitted to letter the ledger"), frappe.PermissionError)


# ── accounts panel ───────────────────────────────────────────────────────────


@frappe.whitelist()
def get_accounts(
	company: str, category: str = "Tous", search: str = "", hide_settled: int = 1, sort_by: str = "numero"
) -> dict:
	"""Left panel: one card per account with its balance and the number of
	non-lettered lines, plus the panel totals."""
	_check_read()
	rows = frappe.get_all(
		LEDGER,
		fields=["account", "debit", "credit", "lettrage_status"],
		filters=[["company", "=", company]] if company else [],
	)
	by_account: dict[str, Any] = {}
	for row in rows:
		agg = by_account.setdefault(
			row.account, {"total_debit": 0.0, "total_credit": 0.0, "a_lettrer": 0}
		)
		agg["total_debit"] += flt(row.debit)
		agg["total_credit"] += flt(row.credit)
		if row.lettrage_status == "Non lettre":
			agg["a_lettrer"] += 1

	accounts = []
	for account in frappe.get_all(
		"Chart of Account",
		filters={"is_group": 0, "disabled": 0},
		fields=["name", "account_number", "account_name", "account_type"],
		order_by="account_number asc",
	):
		if category == "Autres":
			if not _in_category(account.account_number, "Autres"):
				continue
		elif category != "Tous" and not _in_category(account.account_number, category):
			continue
		if search and search.lower() not in (
			(f"{account.account_number or ''} {account.account_name or ''}").lower()
		):
			continue

		agg = by_account.get(account.name)
		a_lettrer = int(agg.a_lettrer) if agg else 0
		solde = flt(agg.total_debit - agg.total_credit, 3) if agg else 0.0
		accounts.append(
			{
				"account": account.name,
				"number": account.account_number or "",
				"name": account.account_name or account.name,
				"solde": solde,
				"side": "D" if solde >= 0 else "C",
				"a_lettrer": a_lettrer,
				"type": account.account_type or "",
			}
		)

	hidden = 0
	if hide_settled:
		before = len(accounts)
		accounts = [a for a in accounts if a["a_lettrer"] > 0]
		hidden = before - len(accounts)

	if sort_by == "montant":
		accounts.sort(key=lambda a: abs(a["solde"]), reverse=True)
	elif sort_by == "libelle":
		accounts.sort(key=lambda a: a["name"].lower())
	else:
		accounts.sort(key=lambda a: a["number"] or a["name"])

	return {
		"accounts": accounts,
		"totals": {
			"account_count": len(accounts),
			"hidden_settled": hidden,
			"total_a_lettrer": sum(a["a_lettrer"] for a in accounts),
		},
	}


def _in_category(account_number: str | None, category: str) -> bool:
	"""Category membership by PCG prefix; 'Autres' is the complement."""
	number = (account_number or "").strip()
	if category == "Autres":
		return bool(number) and not any(
			number.startswith(prefix) for prefix in CATEGORY_PREFIXES.values()
		)
	prefix = CATEGORY_PREFIXES.get(category)
	return bool(prefix) and number.startswith(prefix)


# ── lines panel ──────────────────────────────────────────────────────────────


@frappe.whitelist()
def get_lines(company: str, account: str, tab: str = "Toutes", filters: str = "{}", page: int = 1, page_size: int = 25) -> dict:
	"""Right panel rows: paged lines of one account ("ALL" = overview of the
	whole company) with a running balance, plus the header stats."""
	_check_read()
	parsed = json.loads(filters or "{}")
	ledger_filters: list[list] = [["company", "=", company]] if company else []
	if account and account != "ALL":
		ledger_filters.append(["account", "=", account])

	status_map = {
		"Non lettrees": "Non lettre",
		"Partielles": "Partiel",
		"Lettrees": "Lettre",
	}
	if tab in status_map:
		ledger_filters.append(["lettrage_status", "=", status_map[tab]])

	if parsed.get("from_date"):
		ledger_filters.append(["posting_date", ">=", parsed["from_date"]])
	if parsed.get("to_date"):
		ledger_filters.append(["posting_date", "<=", parsed["to_date"]])
	if parsed.get("journal"):
		ledger_filters.append(["journal", "=", parsed["journal"]])
	if parsed.get("libelle"):
		ledger_filters.append(["libelle", "like", f"%{parsed['libelle']}%"])

	or_filters: list[list] = []
	if parsed.get("amount_min"):
		or_filters.append(["debit", ">=", flt(parsed["amount_min"])])
		or_filters.append(["credit", ">=", flt(parsed["amount_min"])])
	if parsed.get("amount_max"):
		or_filters.append(["debit", "<=", flt(parsed["amount_max"])])
		or_filters.append(["credit", "<=", flt(parsed["amount_max"])])

	all_rows = frappe.get_all(
		LEDGER,
		filters=ledger_filters,
		or_filters=or_filters,
		fields=[
			"name",
			"posting_date",
			"journal",
			"mvt",
			"ref_doc",
			"libelle",
			"debit",
			"credit",
			"lettrage",
			"lettrage_status",
			"pointe",
			"account",
		],
		order_by="posting_date asc, creation asc",
	)

	running: dict[str, float] = {}
	for row in all_rows:
		key = row.account if (account and account != "ALL") else ""
		running[key] = flt(running.get(key, 0.0) + flt(row.debit) - flt(row.credit), 3)
		row["solde_prog"] = running[key]

	total = len(all_rows)
	solde = flt(sum(flt(r.debit) - flt(r.credit) for r in all_rows), 3)
	non_lettre = sum(1 for r in all_rows if r.lettrage_status == "Non lettre")
	a_lettrer = sum(1 for r in all_rows if r.lettrage_status in ("Non lettre", "Partiel"))

	page = max(int(page or 1), 1)
	page_size = min(max(int(page_size or 25), 1), 250)
	start = (page - 1) * page_size
	rows = all_rows[start : start + page_size]

	for row in rows:
		row["date"] = getdate(row.posting_date).strftime("%d/%m/%Y") if row.posting_date else ""
		row["side"] = "D" if row.solde_prog >= 0 else "C"

	return {
		"rows": rows,
		"total": total,
		"page": page,
		"page_size": page_size,
		"stats": {"solde": solde, "non_lettre": non_lettre, "lignes_a_lettrer": a_lettrer},
	}


# ── letter / unletter ────────────────────────────────────────────────────────


@frappe.whitelist()
def letter_lines(company: str, account: str, names: str, allow_partial: int = 0) -> dict:
	"""Letter the selected lines together: balanced → Lettre, otherwise
	Partiel when allowed (the ecart is returned in the error otherwise).
	Selections touching a partial group pull the whole group in and reuse
	its group and letter code."""
	_check_write()
	selected = json.loads(names or "[]")
	if len(selected) < 2:
		frappe.throw(_("Select at least two lines to letter."))

	lines = _fetch_lines(selected)
	if not lines:
		frappe.throw(_("No ledger lines found for the selection."))

	companies = {line.company for line in lines}
	accounts = {line.account for line in lines}
	if len(companies) > 1 or len(accounts) > 1:
		frappe.throw(_("All lettered lines must belong to the same company and account."))
	if company and companies != {company}:
		frappe.throw(_("The lines belong to another company."))
	if account and accounts != {account}:
		frappe.throw(_("The lines belong to another account."))

	# a partial group joins whole: its rows and its letter code are reused
	group_name = None
	partial_groups = {
		line.lettrage_groupe
		for line in lines
		if line.lettrage_status == "Partiel" and line.lettrage_groupe
	}
	if len(partial_groups) > 1:
		frappe.throw(_("The selection spans several partial groups; letter them separately."))
	if partial_groups:
		group_name = partial_groups.pop()
		group_rows = frappe.get_all(LEDGER, filters={"lettrage_groupe": group_name}, pluck="name")
		lines = _fetch_lines(sorted(set([line.name for line in lines]) | set(group_rows)))

	any_pointe = any(line.pointe for line in lines)
	if any_pointe:
		frappe.throw(_("Ecriture pointee: departager d'abord."))

	total_debit = flt(sum(flt(line.debit) for line in lines), 3)
	total_credit = flt(sum(flt(line.credit) for line in lines), 3)
	ecart = flt(total_debit - total_credit, 3)

	if abs(ecart) <= TOLERANCE:
		status = "Lettre"
	elif int(allow_partial or 0):
		status = "Partiel"
	else:
		frappe.throw(
			_("Ecart de {0}: lettrage non equilibre (autorisez le lettrage partiel pour continuer).").format(
				f"{ecart:,.3f}"
			)
		)

	today = nowdate()
	if group_name:
		code = frappe.db.get_value("Lettrage Groupe", group_name, "code")
		frappe.db.set_value(
			"Lettrage Groupe",
			group_name,
			{
				"status": status,
				"total_debit": total_debit,
				"total_credit": total_credit,
				"ecart": ecart,
				"line_count": len(lines),
			},
		)
	else:
		code = _next_code(company or next(iter(companies)), next(iter(accounts)))
		group = frappe.get_doc(
			{
				"doctype": "Lettrage Groupe",
				"company": next(iter(companies)),
				"account": next(iter(accounts)),
				"code": code,
				"date": today,
				"user": frappe.session.user,
				"status": status,
				"mode": "Manuel",
				"rule": "",
				"total_debit": total_debit,
				"total_credit": total_credit,
				"ecart": ecart,
				"line_count": len(lines),
			}
		)
		group.insert(ignore_permissions=True)
		group_name = group.name

	for line in lines:
		frappe.db.set_value(
			LEDGER,
			line.name,
			{
				"lettrage": code,
				"lettrage_status": status,
				"lettrage_date": today,
				"lettrage_groupe": group_name,
			},
			update_modified=False,
		)

	return {
		"group": group_name,
		"code": code,
		"status": status,
		"ecart": ecart,
		"count": len(lines),
	}


@frappe.whitelist()
def unletter(company: str, names: str) -> dict:
	"""Clear the letter on the selected lines and mark their groups Delettre
	(groups stay for audit)."""
	_check_write()
	selected = json.loads(names or "[]")
	if not selected:
		frappe.throw(_("No lines selected."))
	lines = _fetch_lines(selected)

	today = nowdate()
	groups = {line.lettrage_groupe for line in lines if line.lettrage_groupe}
	for line in lines:
		frappe.db.set_value(
			LEDGER,
			line.name,
			{"lettrage": "", "lettrage_status": "Non lettre", "lettrage_date": None, "lettrage_groupe": None},
			update_modified=False,
		)
	for group in groups:
		frappe.db.set_value("Lettrage Groupe", group, {"status": "Delettre"}, update_modified=False)

	return {"cleared": len(lines), "groups": sorted(groups)}


@frappe.whitelist()
def suggest(company: str, account: str) -> dict:
	"""Candidate sets that would balance — rules only, nothing is written."""
	_check_read()
	lines = _account_lines(company, account)
	candidates = run_rules(lines, ["R1", "R2"])
	out = []
	for candidate in candidates[:SUGGEST_LIMIT]:
		out.append(
			{
				"rule": candidate["rule"],
				"key": candidate["key"],
				"names": [line["name"] for line in candidate["lines"]],
				"count": len(candidate["lines"]),
				"total_debit": candidate["total_debit"],
				"total_credit": candidate["total_credit"],
				"preview": [
					{"mvt": line["mvt"], "ref_doc": line["ref_doc"], "debit": line["debit"], "credit": line["credit"]}
					for line in candidate["lines"][:6]
				],
			}
		)
	return {"candidates": out, "total_candidates": len(candidates)}


# ── pointage ─────────────────────────────────────────────────────────────────


@frappe.whitelist()
def toggle_pointe(names: str, value: int) -> dict:
	"""Pointage is a treasury-only flag (Bank/Cash accounts)."""
	_check_write()
	selected = json.loads(names or "[]")
	if not selected:
		frappe.throw(_("No lines selected."))
	lines = _fetch_lines(selected)

	value = 1 if int(value or 0) else 0
	account_types = {
		row.name: row.account_type
		for row in frappe.get_all(
			"Chart of Account",
			filters={"name": ("in", {line.account for line in lines})},
			fields=["name", "account_type"],
		)
	}
	non_treasury = [
		line.name
		for line in lines
		if account_types.get(line.account) not in TREASURY_ACCOUNT_TYPES
	]
	if non_treasury:
		frappe.throw(
			_("Le pointage est reserve aux comptes de tresorerie ({0}).").format(
				", ".join(non_treasury[:3])
			)
		)

	today = nowdate() if value else None
	for line in lines:
		frappe.db.set_value(
			LEDGER, line.name, {"pointe": value, "pointe_date": today}, update_modified=False
		)
	return {"pointed": len(lines), "value": value}


# ── automatic lettrage ───────────────────────────────────────────────────────


@frappe.whitelist()
def run_auto_lettrage(company: str, category: str = "Tous", account: str = "ALL", rules: str = '["R1", "R2"]') -> dict:
	"""Background pass: per account in scope, apply the rules and letter the
	balanced sets (groups mode Automatique). Progress is published realtime."""
	_check_write()
	user = frappe.session.user
	frappe.enqueue(
		method="erpnext.custom_modules.reports.doctype.lettrage.lettrage._auto_lettrage_job",
		queue="long",
		is_async=True,
		enqueue_after_commit=True,
		company=company,
		category=category,
		account=account,
		rules=json.loads(rules or '["R1", "R2"]'),
		user=user,
	)
	return {"started": 1}


def _auto_lettrage_job(company: str, category: str, account: str, rules: list[str], user: str) -> None:
	frappe.set_user(user)
	scope = _scope_accounts(company, category, account)
	groups_created = 0
	lines_lettered = 0
	skipped = 0
	total = len(scope) if scope else 0

	for i, acct in enumerate(scope or [], start=1):
		lines = _account_lines(company, acct)
		candidates = run_rules(lines, rules)
		for candidate in candidates:
			code = _next_code(company, acct)
			group = frappe.get_doc(
				{
					"doctype": "Lettrage Groupe",
					"company": company,
					"account": acct,
					"code": code,
					"date": nowdate(),
					"user": user,
					"status": "Lettre",
					"mode": "Automatique",
					"rule": candidate["rule"],
					"total_debit": candidate["total_debit"],
					"total_credit": candidate["total_credit"],
					"ecart": flt(candidate["total_debit"] - candidate["total_credit"], 3),
					"line_count": len(candidate["lines"]),
				}
			)
			group.insert(ignore_permissions=True)
			groups_created += 1
			for line in candidate["lines"]:
				frappe.db.set_value(
					LEDGER,
					line["name"],
					{
						"lettrage": code,
						"lettrage_status": "Lettre",
						"lettrage_date": nowdate(),
						"lettrage_groupe": group.name,
					},
					update_modified=False,
				)
			lines_lettered += len(candidate["lines"])
		skipped += len(lines) - sum(
			len(c["lines"]) for c in candidates
		)
		frappe.publish_realtime(
			"lettrage_progress",
			{
				"phase": "run",
				"progress": round(i / total * 100) if total else 100,
				"current": i,
				"total": total,
				"groups": groups_created,
				"lines": lines_lettered,
			},
			user=user,
		)

	frappe.publish_realtime(
		"lettrage_progress",
		{
			"phase": "done",
			"progress": 100,
			"groups": groups_created,
			"lines": lines_lettered,
			"skipped": skipped,
		},
		user=user,
	)


@frappe.whitelist()
def run_auto_delettrage(company: str, category: str = "Tous", account: str = "ALL") -> dict:
	"""Background pass: undo every Automatique group in scope."""
	_check_write()
	user = frappe.session.user
	frappe.enqueue(
		method="erpnext.custom_modules.reports.doctype.lettrage.lettrage._auto_delettrage_job",
		queue="long",
		is_async=True,
		enqueue_after_commit=True,
		company=company,
		category=category,
		account=account,
		user=user,
	)
	return {"started": 1}


def _auto_delettrage_job(company: str, category: str, account: str, user: str) -> None:
	frappe.set_user(user)
	scope = _scope_accounts(company, category, account)
	filters: list[list] = [["company", "=", company], ["mode", "=", "Automatique"], ["status", "!=", "Delettre"]]
	if account and account != "ALL":
		filters.append(["account", "=", account])
	elif scope is not None:
		filters.append(["account", "in", scope])
	groups = frappe.get_all("Lettrage Groupe", filters=filters, pluck="name")
	total = len(groups)
	cleared = 0

	for i, group in enumerate(groups, start=1):
		rows = frappe.get_all(LEDGER, filters={"lettrage_groupe": group}, pluck="name")
		for name in rows:
			frappe.db.set_value(
				LEDGER,
				name,
				{"lettrage": "", "lettrage_status": "Non lettre", "lettrage_date": None, "lettrage_groupe": None},
				update_modified=False,
			)
		frappe.db.set_value("Lettrage Groupe", group, {"status": "Delettre"}, update_modified=False)
		cleared += len(rows)
		frappe.publish_realtime(
			"lettrage_progress",
			{"phase": "run", "progress": round(i / total * 100) if total else 100, "current": i, "total": total, "lines": cleared},
			user=user,
		)

	frappe.publish_realtime(
		"lettrage_progress", {"phase": "done", "progress": 100, "groups": total, "lines": cleared, "skipped": 0}, user=user
	)


# ── shared helpers ───────────────────────────────────────────────────────────


def _fetch_lines(names: list[str]) -> list[frappe._dict]:
	return frappe.get_all(
		LEDGER,
		filters={"name": ("in", names)},
		fields=[
			"name",
			"company",
			"account",
			"posting_date",
			"mvt",
			"ref_doc",
			"libelle",
			"debit",
			"credit",
			"lettrage",
			"lettrage_status",
			"lettrage_groupe",
			"pointe",
		],
		order_by="posting_date asc, creation asc",
	)


def _account_lines(company: str, account: str) -> list[dict]:
	"""Non-lettered lines of one account, oldest first (rule input)."""
	return frappe.get_all(
		LEDGER,
		filters=[
			["company", "=", company],
			["account", "=", account],
			["lettrage_status", "=", "Non lettre"],
		],
		fields=["name", "posting_date", "ref_doc", "libelle", "debit", "credit", "lettrage_status"],
		order_by="posting_date asc, creation asc",
	)


def _scope_accounts(company: str, category: str, account: str) -> list[str] | None:
	"""Accounts the automatic passes cover: one account, the category, or
	everything (None = all accounts with ledger rows)."""
	if account and account != "ALL":
		return [account]
	if category and category not in ("Tous", "Autres"):
		prefix = CATEGORY_PREFIXES.get(category)
		return frappe.get_all("Chart of Account", filters={"account_number": ("like", f"{prefix}%")}, pluck="name")
	rows = frappe.get_all(LEDGER, filters=[["company", "=", company]], fields=["distinct account as account"])
	return [row.account for row in rows]


def _next_code(company: str, account: str) -> str:
	"""The next letter code for one (company, account): A..Z then AA..ZZ.

	Serialized by a parameterized SELECT ... FOR UPDATE on the account's
	latest group row; a MySQL named lock covers the empty-table case where
	no row exists to lock yet."""
	existing = frappe.db.sql(
		"""select code
			from `tabLettrage Groupe`
			where company = %(company)s and account = %(account)s
			order by creation desc, code desc
			limit 1
			for update""",
		{"company": company, "account": account},
		pluck="code",
	)
	if not existing:
		lock_key = f"lettrage_{company}_{account}"
		frappe.db.sql("select get_lock(%(key)s, 10) as locked", {"key": lock_key})
		try:
			existing = frappe.db.sql(
				"""select code
					from `tabLettrage Groupe`
					where company = %(company)s and account = %(account)s
					order by creation desc, code desc
					limit 1""",
				{"company": company, "account": account},
				pluck="code",
			)
		finally:
			frappe.db.sql("select release_lock(%(key)s)", {"key": lock_key})

	code = _increment_code(existing[0] if existing else None)
	if not code:
		frappe.throw(_("Plus de codes de lettrage disponibles pour {0} - {1}.").format(company, account))
	return code


def _increment_code(current: str | None) -> str | None:
	"""A..Z then AA..ZZ: base-26 increment of the letter code."""
	if not current:
		return "A"
	index = 0
	for char in current.upper():
		if not "A" <= char <= "Z":
			return None
		index = index * 26 + (ord(char) - ord("A") + 1)
	index += 1
	letters = ""
	while index > 0:
		index, remainder = divmod(index - 1, 26)
		letters = chr(ord("A") + remainder) + letters
	if len(letters) > 2:
		return None
	return letters
