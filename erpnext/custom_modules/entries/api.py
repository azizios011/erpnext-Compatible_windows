# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Whitelisted helpers for the Entries forms ("Saisie des ecritures").

Every argument carries a full type annotation — Frappe rejects whitelisted
methods without them.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.custom_modules.entries.entry_base import JOURNAL_CODE_BY_DOCTYPE
from erpnext.custom_modules.facturation.facturation_base import ENTRY_DOCTYPE_BY_DOCTYPE

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
	defaults: dict = {"journal": journal, "mvt": "", "ref_doc": "", "attachment": "", "lines": []}

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


@frappe.whitelist()
def get_list_totaux(doctype: str, filters: str = "", or_filters: str = "") -> dict:
	"""Aggregate the Totaux bar over the list's currently filtered rows.

	`filters`/`or_filters` are the list view's own filter JSON
	([[doctype, field, op, value], ...]); they run through frappe.get_list
	(never raw SQL) with a read permission check on the doctype.
	"""
	if doctype not in JOURNAL_CODE_BY_DOCTYPE:
		frappe.throw(_("{0} is not an Entries document").format(doctype))
	if not frappe.has_permission(doctype, "read"):
		frappe.throw(_("Not permitted to read {0}").format(doctype), frappe.PermissionError)

	parsed = json.loads(filters or "[]")
	parsed_or = json.loads(or_filters or "[]")
	rows = frappe.get_list(
		doctype,
		filters=parsed,
		or_filters=parsed_or,
		fields=["name", "total_debit", "total_credit"],
		limit=0,
	)
	total_debit = flt(sum(flt(row.get("total_debit")) for row in rows), 3)
	total_credit = flt(sum(flt(row.get("total_credit")) for row in rows), 3)
	return {
		"count": len(rows),
		"total_debit": total_debit,
		"total_credit": total_credit,
		"solde": flt(total_debit - total_credit, 3),
	}
