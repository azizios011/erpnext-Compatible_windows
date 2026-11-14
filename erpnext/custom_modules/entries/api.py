# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Whitelisted helpers for the Entries forms ("Saisie des ecritures").

Every argument carries a full type annotation — Frappe rejects whitelisted
methods without them.
"""

import json

import frappe
from frappe import _

from erpnext.custom_modules.entries.entry_base import JOURNAL_CODE_BY_DOCTYPE, PAGE_BY_ENTRY_DOCTYPE, PARTY_RULE_BY_DOCTYPE
from erpnext.custom_modules.facturation.facturation_base import ENTRY_DOCTYPE_BY_DOCTYPE
from erpnext.custom_modules.organization.context import (
	context_for_read,
	require_context,
	validate_exercice_open,
)

# Releve Vente Detail field feeding each non-manual amount source
AMOUNT_SOURCE_FIELD = {
	"Total TTC": "ttc",
	"Total HT": "ht",
	"Remise": "remise",
	"Net HT": "tot_net_ht",
	"Montant TVA": "montant_tva",
}


@frappe.whitelist()
def get_entry_defaults(entry_doctype: str, source_doctype: str = "", source_name: str = "") -> dict:
	"""Defaults for a new, unsaved entry form: journal, mirrors of the source
	document and the default Journal Model's lines (accounts and sides only,
	amounts left empty for the human)."""
	if source_doctype and ENTRY_DOCTYPE_BY_DOCTYPE.get(source_doctype) != entry_doctype:
		frappe.throw(
			_("{0} documents take their entries from {1}, not {2}.").format(
				source_doctype, ENTRY_DOCTYPE_BY_DOCTYPE.get(source_doctype, _("no entry doctype")), entry_doctype
			)
		)

	journal = JOURNAL_CODE_BY_DOCTYPE.get(entry_doctype, "")
	rule = PARTY_RULE_BY_DOCTYPE.get(entry_doctype, {})
	defaults: dict = {
		"journal": journal,
		"tiers_prefix": rule.get("prefix", ""),
		"tiers_side": rule.get("side", ""),
		"tiers_label": rule.get("label", ""),
		"mvt": "",
		"ref_doc": "",
		"attachment": "",
		"lines": [],
	}

	if source_doctype and source_name:
		source = frappe.get_doc(source_doctype, source_name)  # enforces read permission
		defaults["mvt"] = source.get("mvt") or ""
		defaults["ref_doc"] = source.get("reference_number") or ""
		defaults["attachment"] = source.get("attachment") or ""

	model_name = frappe.db.get_value("Journal Model", {"journal": journal, "is_default": 1}, "name")
	if model_name:
		doc = frappe.get_doc("Journal Model", model_name)
		defaults["lines"] = [
			{
				"account": line.account,
				"side": line.side,
				"libelle": line.libelle or "",
				"amount_source": line.amount_source or "Manual",
			}
			for line in doc.lines
		]
	return defaults


@frappe.whitelist()
def get_model_lines(source_doctype: str, source_name: str, journal: str = "") -> dict:
	"""Releve Vente sources: group the Releve Vente Detail rows by operation,
	match each group against the Journal Models of the journal
	(match_keyword contained in the operation, case-insensitive) and resolve
	the model's amount sources from the group's summed figures. Groups
	without a matching model come back in `warnings` for manual entry."""
	if source_doctype != "Releve Vente":
		return {"lines": [], "warnings": []}

	journal = journal or JOURNAL_CODE_BY_DOCTYPE.get("Receivable Transaction", "VT")
	details = frappe.get_all(
		"Releve Vente Detail",
		filters={"parent": source_name, "parenttype": "Releve Vente"},
		fields=["operation", "ttc", "ht", "remise", "tot_net_ht", "montant_tva"],
		order_by="idx asc",
	)

	groups: dict[str, dict] = {}
	for row in details:
		operation = row.operation or ""
		sums = groups.setdefault(
			operation, {"ttc": 0.0, "ht": 0.0, "remise": 0.0, "tot_net_ht": 0.0, "montant_tva": 0.0}
		)
		for field in ("ttc", "ht", "remise", "tot_net_ht", "montant_tva"):
			sums[field] += row.get(field) or 0.0

	models = frappe.get_all(
		"Journal Model",
		filters={"journal": journal},
		fields=["name", "model_name", "match_keyword"],
		order_by="is_default desc, creation asc",
	)

	lines: list[dict] = []
	warnings: list[str] = []
	for operation, sums in groups.items():
		model = next(
			(
				m
				for m in models
				if m.match_keyword and m.match_keyword.lower() in (operation or "").lower()
			),
			None,
		)
		if not model:
			warnings.append(operation or _("(blank operation)"))
			continue
		for model_line in frappe.get_doc("Journal Model", model.name).lines:
			field = AMOUNT_SOURCE_FIELD.get(model_line.amount_source or "Manual")
			amount = sums.get(field, 0.0) if field else 0.0
			debit, credit = (amount, 0.0) if (model_line.side or "Debit") == "Debit" else (0.0, amount)
			lines.append(
				{
					"account": model_line.account,
					"side": model_line.side or "Debit",
					"libelle": model_line.libelle or operation,
					"debit": debit,
					"credit": credit,
				}
			)
	return {"lines": lines, "warnings": warnings}


@frappe.whitelist()
def get_journal_models(journal: str) -> list[dict]:
	"""Journal Models of one journal, for the Appel Modele dialog."""
	return frappe.get_all(
		"Journal Model",
		filters={"journal": journal},
		fields=["name", "model_name", "is_default"],
		order_by="is_default desc, model_name asc",
	)


@frappe.whitelist()
def get_journal_model_lines(model: str) -> dict:
	"""One Journal Model's lines, for loading into the entry grid."""
	doc = frappe.get_doc("Journal Model", model)  # enforces read permission
	return {
		"journal": doc.journal,
		"model_name": doc.model_name,
		"lines": [
			{
				"account": line.account,
				"side": line.side or "Debit",
				"libelle": line.libelle or "",
				"amount_source": line.amount_source or "Manual",
				"debit": 0.0,
				"credit": 0.0,
			}
			for line in doc.lines
		],
	}


@frappe.whitelist()
def save_journal_model(journal: str, model_name: str, lines: str) -> dict:
	"""Enreg. Modele: store the current grid lines (accounts and sides) as a
	new Journal Model of the journal. `lines` arrives as a JSON array string."""
	parsed = json.loads(lines or "[]")
	if not parsed:
		frappe.throw(_("No lines to save into the model."))
	doc = frappe.get_doc(
		{
			"doctype": "Journal Model",
			"journal": journal,
			"model_name": model_name,
			"lines": [
				{
					"account": line.get("account"),
					"side": line.get("side") or "Debit",
					"libelle": line.get("libelle") or "",
					"amount_source": line.get("amount_source") or "Manual",
				}
				for line in parsed
			],
		}
	)
	doc.insert()  # permission-checked
	return {"name": doc.name}


def _can_modify(entry_doctype: str, name: str = "") -> bool:
	"""Write permission on the entry doctype AND an open context Exercice —
	the two gates the inspect view needs before offering its Modifier button."""
	try:
		context = require_context()
		validate_exercice_open(context)
		if name:
			return bool(frappe.has_permission(entry_doctype, "write", doc=name))
		return bool(frappe.has_permission(entry_doctype, "write"))
	except Exception:
		return False


@frappe.whitelist()
def open_entry(entry_doctype: str = "", mode: str = "auto", name: str = "", source_doctype: str = "", source_name: str = "") -> dict:
	"""One resolver for every entry point (Facturation pen and form buttons,
	reports, islands): resolves where an entry opens for the requested mode.

	Input is either a Facturation source (`source_doctype` + `source_name`, the
	entry doctype resolved through ENTRY_DOCTYPE_BY_DOCTYPE) or an entry
	(`entry_doctype` + `name`). `mode`: "auto" (the pen: a source with an entry
	is modified, one without is created), "creation", "modify" or "inspect".

	Returns {"entry_doctype", "mode", "name", "kind", "route", "query",
	"defaults", "can_modify"}: kind "page" drives the payable / receivable
	islands (route + query land in the island's props), kind "form" keeps
	Treasury / Declaration on the classic forms.
	"""
	mode = (mode or "auto").strip().lower()
	if mode not in ("auto", "creation", "modify", "inspect"):
		frappe.throw(_("Unknown mode: {0}.").format(mode))

	# the source's side must match the entry doctype when both are given
	source_side = ENTRY_DOCTYPE_BY_DOCTYPE.get(source_doctype) if source_doctype else ""
	if source_doctype and not source_side:
		frappe.throw(_("{0} is not a Facturation document").format(source_doctype))
	if source_side and entry_doctype and source_side != entry_doctype:
		frappe.throw(
			_("{0} documents take their entries from {1}, not {2}.").format(source_doctype, source_side, entry_doctype)
		)

	target = None
	if mode in ("auto", "creation"):
		if not (source_doctype and source_name):
			frappe.throw(_("auto and creation need a source document (source_doctype + source_name)."))
		# get_entry_target: read permission on the source, require_context(),
		# validate_source_context() and the prefill defaults — reused as-is
		target = get_entry_target(source_doctype, source_name)
		entry_doctype = target["entry_doctype"]

		if mode == "auto":
			mode = "modify" if target["existing_entry"] else "creation"

		if target["existing_entry"]:
			# one entry per source: an explicit creation is refused, with the
			# existing entry named for modify / inspect
			frappe.throw(
				_("{0} {1} already has an entry: {2} — modify or inspect it instead.").format(
					source_doctype, source_name, frappe.bold(target["existing_entry"])
				)
			)
	elif not entry_doctype:
		frappe.throw(_("entry_doctype is required for modify and inspect."))

	if mode in ("modify", "inspect"):
		if not name:
			frappe.throw(_("modify and inspect need an entry name."))
		if not frappe.db.exists(entry_doctype, name):
			frappe.throw(_("The entry {0} does not exist.").format(name), frappe.DoesNotExistError)
		permission_type = "write" if mode == "modify" else "read"
		if not frappe.has_permission(entry_doctype, permission_type, doc=name):
			frappe.throw(
				_("You do not have {0} permission on {1} {2}.").format(permission_type, _(entry_doctype), name),
				frappe.PermissionError,
			)
		# the entry must belong to the user's current Entreprise/Exercice —
		# inspect stays possible on a closed Exercice (only can_modify gates it)
		entry_entreprise, entry_exercice = frappe.db.get_value(entry_doctype, name, ["entreprise", "exercice"])
		entreprise, exercice = context_for_read()
		if entry_entreprise != entreprise or entry_exercice != exercice:
			frappe.throw(
				_("L'ecriture appartient a un autre contexte comptable ({0} · {1}).").format(entry_entreprise, entry_exercice)
			)

	can_modify = _can_modify(entry_doctype, name if mode != "creation" else "")
	defaults = (target or {}).get("defaults", {}) or {}

	if entry_doctype in PAGE_BY_ENTRY_DOCTYPE:
		kind = "page"
		page = PAGE_BY_ENTRY_DOCTYPE[entry_doctype]
		if mode == "creation":
			route = [page, "creation"]
			query = {
				"source_doctype": defaults.get("source_doctype", source_doctype),
				"source_name": defaults.get("source_name", source_name),
				"date_operation": defaults.get("date_operation", "") or "",
				"ref_doc": defaults.get("ref_doc", "") or "",
				"journal": defaults.get("journal", "") or "",
			}
		else:
			route = [page, mode, name]
			query = {}
	else:
		kind = "form"
		query = {}
		if mode == "creation":
			route = [entry_doctype]
		else:
			route = ["Form", entry_doctype, name]

	return {
		"entry_doctype": entry_doctype,
		"mode": mode,
		"name": name or (target or {}).get("existing_entry", ""),
		"kind": kind,
		"route": route,
		"query": query,
		"defaults": defaults,
		"can_modify": can_modify,
	}
