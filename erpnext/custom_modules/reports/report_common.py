# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Helpers shared by the Reports-module script reports (Ledger Data,
Balance): permission gate, the period model clamped to the Exercice, the
grand-livre account-type prefixes and MultiSelectList value parsing."""

from datetime import date, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from erpnext.custom_modules.reports.imported_entries_logic import (
    AUX_CLIENT_PREFIX,
    AUX_FOURNISSEUR_PREFIX,
)

LEDGER_DOCTYPE = "Ecriture Comptable"

# the reports' summary cards carry the base currency (the devise filter
# only narrows the rows)
REPORT_CURRENCY = "TND"

# auxiliary ledgers are the client / supplier account-number prefixes —
# defined in imported_entries_logic.py (the frappe-free single source) and
# re-exported here for the reports

BALANCE_TOLERANCE = 0.0005

MONTHS_FR = {
	"Janvier": 1,
	"Fevrier": 2,
	"Mars": 3,
	"Avril": 4,
	"Mai": 5,
	"Juin": 6,
	"Juillet": 7,
	"Aout": 8,
	"Septembre": 9,
	"Octobre": 10,
	"Novembre": 11,
	"Decembre": 12,
}

QUARTER_MONTHS = {"T1": (1, 3), "T2": (4, 6), "T3": (7, 9), "T4": (10, 12)}


def check_ledger_read_permission() -> None:
	if not frappe.has_permission(LEDGER_DOCTYPE, "read"):
		frappe.throw(_("Not permitted to read the ledger"), frappe.PermissionError)


def exercice_year(context: dict) -> int:
	debut = context.get("date_debut")
	return getdate(debut).year if debut else int(nowdate()[:4])


def resolve_period(filters: dict, context: dict) -> tuple[date, date]:
	"""Every period filter resolves to one (from_date, to_date) pair, clamped
	to the context's Exercice (date_debut..date_fin). The year is the
	Exercice's, not a filter: the period can never leave the Exercice."""
	period_type = filters.get("period_type") or "Mensuelle"
	year = exercice_year(context)
	if period_type == "Personnalisee":
		from_date = getdate(filters.get("from_date"))
		to_date = getdate(filters.get("to_date"))
	elif period_type == "Trimestrielle":
		first, last = QUARTER_MONTHS[filters.get("quarter") or "T1"]
		from_date = date(year, first, 1)
		to_date = date(year, last, 31 if last in (1, 3, 7, 8, 10, 12) else 30)
	elif period_type == "Annuelle":
		from_date = date(year, 1, 1)
		to_date = date(year, 12, 31)
	else:
		# Mensuelle: default to the Exercice's first month when no month comes
		# in (the UI sends one, preselected on the Exercice)
		default_month = getdate(context["date_debut"]).month if context.get("date_debut") else 1
		month = MONTHS_FR.get(filters.get("month") or "", default_month)
		next_month = date(year + (month == 12), (month % 12) + 1, 1)
		from_date = date(year, month, 1)
		to_date = next_month - timedelta(days=1)

	debut = getdate(context["date_debut"]) if context.get("date_debut") else None
	fin = getdate(context["date_fin"]) if context.get("date_fin") else None
	if debut and from_date < debut:
		from_date = debut
	if fin and to_date > fin:
		to_date = fin
	return from_date, to_date


def as_list(value: Any) -> list:
	"""MultiSelectList values arrive as lists or comma-joined strings."""
	if isinstance(value, (list, tuple)):
		return [v for v in value if v]
	return [v.strip() for v in str(value).split(",") if v.strip()]
