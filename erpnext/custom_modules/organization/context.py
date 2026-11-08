# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Axeane accounting context (Definir un contexte comptable).

Per-user defaults selecting the Entreprise and the Fiscal Year the user
works in. Stored through frappe user defaults; exposed to the desk via
bootinfo (extend_bootinfo) and consumed by the axeane_context bundle.
"""

from typing import Any

import frappe
from frappe import _
from frappe.utils import getdate

ENTREPRISE_DEFAULT = "axeane_entreprise"
FISCAL_YEAR_DEFAULT = "axeane_fiscal_year"


def _is_admin() -> bool:
	return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()


def _accessible_entreprises() -> list[frappe._dict]:
	"""Permission-aware Entreprise list: Administrator and System Manager see
	every one; other users only the Entreprises whose Entreprise User child
	rows carry them."""
	if _is_admin():
		return frappe.get_all(
			"Entreprise",
			fields=["name", "raison_sociale", "matricule_fiscal", "status"],
			order_by="raison_sociale asc",
		)
	names = frappe.get_all(
		"Entreprise User", filters={"user": frappe.session.user}, pluck="parent"
	)
	if not names:
		return []
	return frappe.get_all(
		"Entreprise",
		filters={"name": ("in", names)},
		fields=["name", "raison_sociale", "matricule_fiscal", "status"],
		order_by="raison_sociale asc",
	)


def _fiscal_years() -> list[frappe._dict]:
	"""Every enabled Fiscal Year, newest first (there is no Exercice
	doctype: the fiscal year is the core Fiscal Year)."""
	return frappe.get_all(
		"Fiscal Year",
		filters={"disabled": 0},
		fields=["name", "year", "year_start_date", "year_end_date"],
		order_by="year_start_date desc",
	)


def _fiscal_year_containing_today(fiscal_years: list[frappe._dict]) -> str:
	today = getdate(frappe.utils.nowdate())
	for fiscal_year in fiscal_years:
		if fiscal_year.year_start_date and fiscal_year.year_end_date:
			if getdate(fiscal_year.year_start_date) <= today <= getdate(fiscal_year.year_end_date):
				return fiscal_year.name
	return ""


def _resolve(entreprises: list, fiscal_years: list) -> tuple[str, str]:
	entreprise = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or ""
	if entreprise not in {row.name for row in entreprises}:
		entreprise = entreprises[0].name if entreprises else ""

	fiscal_year = frappe.defaults.get_user_default(FISCAL_YEAR_DEFAULT) or ""
	if fiscal_year not in {row.name for row in fiscal_years}:
		fiscal_year = _fiscal_year_containing_today(fiscal_years) or (
			fiscal_years[0].name if fiscal_years else ""
		)
	return entreprise, fiscal_year


@frappe.whitelist()
def get_context() -> dict[str, Any]:
	"""The current context plus the lists the selector offers."""
	_check_read()
	entreprises = _accessible_entreprises()
	fiscal_years = _fiscal_years()
	entreprise, fiscal_year = _resolve(entreprises, fiscal_years)

	row = next((row for row in entreprises if row.name == entreprise), None)
	year_row = next((row for row in fiscal_years if row.name == fiscal_year), None)

	return {
		"entreprise": entreprise,
		"entreprise_label": (row.raison_sociale or row.name) if row else "",
		"matricule_fiscal": (row.matricule_fiscal or "") if row else "",
		"fiscal_year": fiscal_year,
		"year_start_date": year_row.year_start_date if year_row else None,
		"year_end_date": year_row.year_end_date if year_row else None,
		"entreprises": [
			{"name": row.name, "label": row.raison_sociale or row.name} for row in entreprises
		],
		"fiscal_years": [{"name": row.name, "label": row.name} for row in fiscal_years],
	}


@frappe.whitelist()
def set_context(entreprise: str = "", fiscal_year: str = "") -> dict[str, Any]:
	"""Validate and store the user's context, then return the fresh one."""
	_check_read()
	entreprises = _accessible_entreprises()
	if entreprise:
		if entreprise not in {row.name for row in entreprises}:
			frappe.throw(_("Vous n'avez pas acces a l'entreprise {0}.").format(entreprise))
		frappe.defaults.set_user_default(ENTREPRISE_DEFAULT, entreprise)

	fiscal_years = _fiscal_years()
	if fiscal_year:
		if fiscal_year not in {row.name for row in fiscal_years}:
			frappe.throw(_("L'exercice {0} n'existe pas ou est desactive.").format(fiscal_year))
		frappe.defaults.set_user_default(FISCAL_YEAR_DEFAULT, fiscal_year)

	return get_context()


def get_accounting_context() -> dict[str, Any]:
	"""Plain helper for other modules: the current (resolved) context without
	enforcing read permission. Not wired anywhere yet."""
	entreprises = _accessible_entreprises()
	fiscal_years = _fiscal_years()
	entreprise, fiscal_year = _resolve(entreprises, fiscal_years)
	row = next((row for row in entreprises if row.name == entreprise), None)
	year_row = next((row for row in fiscal_years if row.name == fiscal_year), None)
	return {
		"entreprise": entreprise,
		"entreprise_label": (row.raison_sociale or row.name) if row else "",
		"matricule_fiscal": (row.matricule_fiscal or "") if row else "",
		"fiscal_year": fiscal_year,
		"year_start_date": year_row.year_start_date if year_row else None,
		"year_end_date": year_row.year_end_date if year_row else None,
	}


def _check_read() -> None:
	# the selector itself is desk-wide: every logged-in user may read its own
	# context; the Entreprise visibility rules live in _accessible_entreprises
	if frappe.session.user in ("Guest", None):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def boot_context(bootinfo: frappe._dict) -> None:
	"""extend_bootinfo entry: ships the context and its option lists so the
	dock selector never waits on a round trip."""
	try:
		bootinfo.axeane_context = get_context()
	except Exception:
		frappe.log_error("axeane boot context failed", frappe.get_traceback())
