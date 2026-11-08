# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Axeane accounting context (Definir un contexte comptable).

Per-user defaults selecting the Entreprise and the Exercice the user works
in. Stored through frappe user defaults; exposed to the desk via bootinfo
(extend_bootinfo) and consumed by the axeane_context bundle. The Exercice
is our own doctype (module Organization); core Fiscal Year is no longer
surfaced anywhere.
"""

from typing import Any

import frappe
from frappe import _
from frappe.utils import getdate

ENTREPRISE_DEFAULT = "axeane_entreprise"
EXERCICE_DEFAULT = "axeane_exercice"


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


def _exercices_of(entreprise: str) -> list[frappe._dict]:
	"""The Entreprise's Exercices, newest first."""
	return frappe.get_all(
		"Exercice",
		filters={"entreprise": entreprise},
		fields=["name", "libelle", "status", "date_debut", "date_fin"],
		order_by="date_debut desc",
	)


def _exercice_containing_today(exercices: list[frappe._dict]) -> str:
	today = getdate(frappe.utils.nowdate())
	for exercice in exercices:
		if exercice.date_debut and exercice.date_fin:
			if getdate(exercice.date_debut) <= today <= getdate(exercice.date_fin):
				return exercice.name
	return ""


def _current_exercice_for(entreprise: str) -> str:
	"""The Entreprise's current Exercice: the one containing today, else the
	latest, else empty."""
	exercices = _exercices_of(entreprise)
	return _exercice_containing_today(exercices) or (exercices[0].name if exercices else "")


def _resolve(entreprises: list, old_entreprise: str) -> tuple[str, str]:
	"""(entreprise, exercice) from the user defaults: an inaccessible
	Entreprise falls back to the first accessible one, and a changed
	Entreprise carries its own current Exercice."""
	entreprise = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or ""
	if entreprise not in {row.name for row in entreprises}:
		entreprise = entreprises[0].name if entreprises else ""

	if entreprise != old_entreprise:
		# switching Entreprise carries that Entreprise's own exercice
		exercice = _current_exercice_for(entreprise)
		if entreprise:
			frappe.defaults.set_user_default(EXERCICE_DEFAULT, exercice)
		return entreprise, exercice

	exercice = frappe.defaults.get_user_default(EXERCICE_DEFAULT) or ""
	exercice_names = {row.name for row in _exercices_of(entreprise)}
	if exercice not in exercice_names:
		exercice = _current_exercice_for(entreprise)
	return entreprise, exercice


@frappe.whitelist()
def get_context() -> dict[str, Any]:
	"""The current context plus the lists the selector offers."""
	_check_read()
	entreprises = _accessible_entreprises()
	old_entreprise = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or ""
	entreprise, exercice = _resolve(entreprises, old_entreprise)

	row = next((row for row in entreprises if row.name == entreprise), None)
	exercices = _exercices_of(entreprise)
	exercice_row = next((row for row in exercices if row.name == exercice), None)

	return {
		"entreprise": entreprise,
		"entreprise_label": (row.raison_sociale or row.name) if row else "",
		"matricule_fiscal": (row.matricule_fiscal or "") if row else "",
		"exercice": exercice,
		"exercice_label": (exercice_row.libelle or exercice) if exercice_row else "",
		"date_debut": exercice_row.date_debut if exercice_row else None,
		"date_fin": exercice_row.date_fin if exercice_row else None,
		"entreprises": [
			{"name": row.name, "label": row.raison_sociale or row.name} for row in entreprises
		],
		"exercices": [
			{"name": row.name, "label": row.libelle or row.name, "status": row.status}
			for row in exercices
		],
	}


@frappe.whitelist()
def set_context(entreprise: str = "", exercice: str = "") -> dict[str, Any]:
	"""Validate and store the user's context, then return the fresh one.

	Only the Entreprise: its own current Exercice is selected. Only the
	Exercice: it must belong to the selected Entreprise."""
	_check_read()
	entreprises = _accessible_entreprises()

	old_entreprise = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or ""
	if entreprise:
		if entreprise not in {row.name for row in entreprises}:
			frappe.throw(_("Vous n'avez pas acces a l'entreprise {0}.").format(entreprise))
		if entreprise != old_entreprise:
			frappe.defaults.set_user_default(ENTREPRISE_DEFAULT, entreprise)
			# the new Entreprise carries its own current Exercice
			frappe.defaults.set_user_default(EXERCICE_DEFAULT, _current_exercice_for(entreprise))

	if exercice:
		target = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or entreprise
		if not target or exercice not in {row.name for row in _exercices_of(target)}:
			frappe.throw(
				_("L'exercice {0} n'appartient pas a l'entreprise {1}.").format(exercice, target)
			)
		frappe.defaults.set_user_default(EXERCICE_DEFAULT, exercice)

	return get_context()


def get_accounting_context() -> dict[str, Any]:
	"""Plain helper for other modules: the current (resolved) context without
	enforcing read permission. Not wired anywhere yet."""
	entreprises = _accessible_entreprises()
	old_entreprise = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or ""
	entreprise, exercice = _resolve(entreprises, old_entreprise)
	row = next((row for row in entreprises if row.name == entreprise), None)
	exercice_row = next((row for row in _exercices_of(entreprise) if row.name == exercice), None)
	return {
		"entreprise": entreprise,
		"entreprise_label": (row.raison_sociale or row.name) if row else "",
		"matricule_fiscal": (row.matricule_fiscal or "") if row else "",
		"exercice": exercice,
		"exercice_label": (exercice_row.libelle or exercice) if exercice_row else "",
		"date_debut": exercice_row.date_debut if exercice_row else None,
		"date_fin": exercice_row.date_fin if exercice_row else None,
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
