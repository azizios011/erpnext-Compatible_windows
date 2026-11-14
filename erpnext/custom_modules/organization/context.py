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
from frappe.utils import cint, formatdate, getdate

ENTREPRISE_DEFAULT = "axeane_entreprise"
EXERCICE_DEFAULT = "axeane_exercice"

# The dock "Contexte comptable" is the only source of Entreprise/Exercice for
# every Facturation / Entries / Reports record; these doctypes carry the
# entreprise and exercice columns and are scoped by scope_conditions.
SCOPED_DOCTYPES = (
	# Facturation upload documents
	"Facture Achat",
	"Releve Achat",
	"RS Achat",
	"Facture Vente",
	"RS Vente",
	"Releve Vente",
	"Releve Bancaire",
	"Remise de Cheque",
	"Versement Espece",
	"Mensuelle",
	# Entries documents
	"Payable Transaction",
	"Receivable Transaction",
	"Treasury Transaction",
	"Declaration Transaction",
	# ledger and lettrage groups
	"Ecriture Comptable",
	"Lettrage Groupe",
)

NO_CONTEXT_MESSAGE = "Choisissez une entreprise et un exercice dans le contexte comptable"
NO_ENTREPRISE_MESSAGE = "Choisissez une entreprise dans le contexte comptable"


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
	type_plan = (frappe.db.get_value("Entreprise", entreprise, "type_plan_comptable") or "Societe") if entreprise else "Societe"
	flux_tresorerie_autorise = cint(
		frappe.db.get_value("Entreprise", entreprise, "modele_flux_tresorerie_autorise")
	)

	return {
		"entreprise": entreprise,
		"entreprise_label": (row.raison_sociale or row.name) if row else "",
		"matricule_fiscal": (row.matricule_fiscal or "") if row else "",
		"exercice": exercice,
		"exercice_label": (exercice_row.libelle or exercice) if exercice_row else "",
		"date_debut": exercice_row.date_debut if exercice_row else None,
		"date_fin": exercice_row.date_fin if exercice_row else None,
		"type_plan": type_plan,
		"flux_tresorerie_autorise": flux_tresorerie_autorise,
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
	type_plan = (frappe.db.get_value("Entreprise", entreprise, "type_plan_comptable") or "Societe") if entreprise else "Societe"
	flux_tresorerie_autorise = cint(
		frappe.db.get_value("Entreprise", entreprise, "modele_flux_tresorerie_autorise")
	)
	return {
		"entreprise": entreprise,
		"entreprise_label": (row.raison_sociale or row.name) if row else "",
		"matricule_fiscal": (row.matricule_fiscal or "") if row else "",
		"exercice": exercice,
		"exercice_label": (exercice_row.libelle or exercice) if exercice_row else "",
		"date_debut": exercice_row.date_debut if exercice_row else None,
		"date_fin": exercice_row.date_fin if exercice_row else None,
		"type_plan": type_plan,
		"flux_tresorerie_autorise": flux_tresorerie_autorise,
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


# ── write-side rules (require_context and friends) ───────────────────────────


def require_context() -> dict[str, Any]:
	"""The strict write context, straight from the user defaults (never
	auto-resolved, never from client input).

	Raises a French error when either the Entreprise or the Exercice is
	missing, when the user may not use that Entreprise (same rule as
	get_context) or when the Exercice does not belong to the Entreprise.
	The Exercice's Ouvert/Cloture status is NOT enforced here — reads of a
	closed Exercice stay possible; call validate_exercice_open on writes.
	"""
	entreprise = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or ""
	exercice = frappe.defaults.get_user_default(EXERCICE_DEFAULT) or ""
	if not entreprise or not exercice:
		frappe.throw(_(NO_CONTEXT_MESSAGE))

	if entreprise not in {row.name for row in _accessible_entreprises()}:
		frappe.throw(_("Vous n'avez pas acces a l'entreprise {0}.").format(entreprise))

	exercice_row = next((row for row in _exercices_of(entreprise) if row.name == exercice), None)
	if exercice_row is None:
		frappe.throw(_("L'exercice {0} n'appartient pas a l'entreprise {1}.").format(exercice, entreprise))

	entreprise_label = frappe.db.get_value("Entreprise", entreprise, "raison_sociale") or entreprise
	return {
		"entreprise": entreprise,
		"entreprise_label": entreprise_label,
		"exercice": exercice,
		"exercice_label": exercice_row.libelle or exercice,
		"status": exercice_row.status or "Ouvert",
		"date_debut": exercice_row.date_debut,
		"date_fin": exercice_row.date_fin,
	}


def context_for_read() -> tuple[str, str]:
	"""(entreprise, exercice) from the user defaults, without enforcing
	anything — the read-side scope for raw queries (reports, lettrage)."""
	return (
		frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or "",
		frappe.defaults.get_user_default(EXERCICE_DEFAULT) or "",
	)


def require_entreprise() -> str:
	"""The Entreprise from the user default only (never client input), for the
	doctypes scoped by Entreprise alone — Chart of Account: a plan comptable
	belongs to the Entreprise across all Exercices. Raises the
	NO_ENTREPRISE_MESSAGE when no Entreprise is set and the no-access message
	when the user may not use it (same rule as require_context)."""
	entreprise = frappe.defaults.get_user_default(ENTREPRISE_DEFAULT) or ""
	if not entreprise:
		frappe.throw(_(NO_ENTREPRISE_MESSAGE))
	if entreprise not in {row.name for row in _accessible_entreprises()}:
		frappe.throw(_("Vous n'avez pas acces a l'entreprise {0}.").format(entreprise))
	return entreprise


def validate_exercice_open(context: dict[str, Any]) -> None:
	"""An entry or a Facturation document may only be created or modified
	while its Exercice is Ouvert."""
	if (context.get("status") or "Ouvert") != "Ouvert":
		frappe.throw(
			_("L'exercice {0} est cloture: creation et modification impossible.").format(
				frappe.bold(context.get("exercice_label") or context.get("exercice") or "")
			)
		)


def validate_date_in_exercice(date_value: Any, context: dict[str, Any], label: str) -> None:
	"""The document date must fall inside the Exercice's date_debut..date_fin."""
	if not date_value:
		return
	debut = getdate(context.get("date_debut")) if context.get("date_debut") else None
	fin = getdate(context.get("date_fin")) if context.get("date_fin") else None
	if not debut or not fin:
		return
	date = getdate(date_value)
	if debut <= date <= fin:
		return
	frappe.throw(
		_("{0} ({1}) est hors de l'exercice {2} ({3} - {4}).").format(
			label,
			frappe.bold(formatdate(date)),
			frappe.bold(context.get("exercice_label") or context.get("exercice") or ""),
			formatdate(debut),
			formatdate(fin),
		)
	)


def validate_source_context(source_doctype: str, source_name: str, context: dict[str, Any]) -> None:
	"""A document opened from a source (pen action) must belong to the same
	Entreprise and Exercice as the source."""
	if not (source_doctype and source_name):
		return
	source = frappe.db.get_value(
		source_doctype, source_name, ["entreprise", "exercice"], as_dict=True
	)
	if not source:
		return
	if (source.entreprise or source.exercice) and (
		source.entreprise != context["entreprise"] or source.exercice != context["exercice"]
	):
		frappe.throw(
			_("Le document source {0} {1} appartient a un autre contexte comptable.").format(
				_(source_doctype), frappe.bold(source_name)
			)
		)


# ── query-side scoping (permission_query_conditions hook) ────────────────────


def scope_conditions(user: str | None = None, doctype: str = "") -> str:
	"""permission_query_conditions hook for every scoped doctype: lists,
	link searches and reports going through get_list only see the records of
	the user's current Entreprise and Exercice. Without a context the scope
	is "1 = 0": the lists come back empty.

	Frappe runs this hook for every user on permission-checked queries
	(db_query.build_match_conditions has no Administrator bypass); queries
	issued with ignore_permissions (system code) skip it by design, and the
	global search reads __global_search directly without this hook.
	"""
	entreprise, exercice = context_for_read()
	if not (entreprise and exercice) or not doctype:
		return "1 = 0"
	# the doctype names carry spaces: the table must be quoted
	table = f"`tab{doctype}`"
	return (
		f"({table}.entreprise = {frappe.db.escape(entreprise)} "
		f"and {table}.exercice = {frappe.db.escape(exercice)})"
	)


def scope_conditions_entreprise(user: str | None = None, doctype: str = "") -> str:
	"""permission_query_conditions hook for the doctypes scoped by Entreprise
	only: same rules as scope_conditions, minus the exercice filter — a plan
	comptable (Chart of Account) belongs to the Entreprise across all
	Exercices and carries no exercice column. Without a context Entreprise
	the scope is "1 = 0"."""
	entreprise, _exercice = context_for_read()
	if not entreprise or not doctype:
		return "1 = 0"
	table = f"`tab{doctype}`"
	return f"{table}.entreprise = {frappe.db.escape(entreprise)}"
