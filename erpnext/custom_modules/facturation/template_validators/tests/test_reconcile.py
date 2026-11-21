# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Unit tests of the reconciliation (base.reconcile) against the Facture
Achat canonical registry: more declared, fewer declared, unused dropped,
inferred added, type conflicts, required coverage. frappe-free and
template-free like base.py itself; runs with pytest or plain python."""

import sys
import os

sys.path.insert(
	0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
)

from erpnext.custom_modules.facturation.template_validators.base import (  # noqa: E402
	reconcile,
	read_python_metadata,
	infer_python,
)
from erpnext.custom_modules.facturation.template_validators.registry import (  # noqa: E402
	get_validator,
)

VALIDATOR = get_validator("Facture Achat")
CANONICAL = VALIDATOR.CANONICAL


def declared(header=None, lines=None, totals=None, extra=None):
	return {
		"document_type": "Facture Achat",
		"template_name": "Test",
		"page": {"size": "A4", "orientation": "portrait"},
		"languages": ["fr"],
		"header": header or {},
		"lines": lines or {},
		"totals": totals or {},
		"extra": extra or {},
	}


def blank_used():
	return {section: {} for section in ("header", "lines", "totals", "extra")}


def with_required(used):
	"""The four required canonical fields count as used so the tests below
	isolate their specific reconciliation rule."""
	used.setdefault("header", {})["invoice_number"] = {"type": None, "strong": False}
	used["header"]["invoice_date"] = {"type": None, "strong": False}
	used.setdefault("lines", {})["designation"] = {"type": None, "strong": False}
	used.setdefault("totals", {})["total_ttc"] = {"type": None, "strong": False}
	return used


def test_more_declared_fields_become_extensions():
	# a header key outside the registry is accepted as an extension field
	# served from data.extra
	decl = declared(header={
		"invoice_number": {"label": "Invoice Number", "type": "text"},
		"client_portal_ref": {"label": "Client Portal Ref", "type": "text"},
	})
	used = blank_used()
	used["header"] = {"invoice_number": {"type": None, "strong": False}}
	used["extra"] = {"client_portal_ref": {"type": None, "strong": False}}
	with_required(used)
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert errors == [], errors
	assert schema["extra"]["client_portal_ref"]["origin"] == "extension"
	assert schema["extra"]["client_portal_ref"]["type"] == "text"
	assert schema["header"]["invoice_number"]["origin"] == "canonical"
	print("OK more declared -> extension")


def test_fewer_declared_fields_is_fine():
	# one template may declare fewer fields: only what it declares or uses
	# enters the schema. The four required canonical fields are still used
	# (inferred, since not declared) and the optional ones stay out entirely.
	decl = declared(header={"currency": {"label": "Currency", "type": "text"}})
	used = blank_used()
	used["header"] = {
		"currency": {"type": None, "strong": False},
		"invoice_number": {"type": None, "strong": False},
		"invoice_date": {"type": None, "strong": False},
	}
	used["lines"] = {"designation": {"type": None, "strong": False}}
	used["totals"] = {"total_ttc": {"type": None, "strong": False}}
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert errors == [], errors
	# optional canonical fields never touched by the template stay out
	for absent in ("due_date", "order_number", "delivery_number", "supplier_tax_id", "timbre"):
		assert absent not in schema["header"] and absent not in schema["totals"], absent
	assert set(schema["header"].keys()) == {"currency", "invoice_number", "invoice_date"}
	print("OK fewer declared -> small schema, no error")


def test_unused_declared_fields_are_dropped():
	decl = declared(header={
		"invoice_number": {"label": "Invoice Number", "type": "text"},
		"currency": {"label": "Currency", "type": "text"},
	})
	used = blank_used()
	used["header"] = {"invoice_number": {"type": None, "strong": False}}
	with_required(used)
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert errors == [], errors
	assert "currency" not in schema["header"]
	assert "invoice_number" in schema["header"]
	assert any("currency" in warning and "dropped" in warning for warning in warnings)
	print("OK declared but unused -> dropped with a warning")


def test_used_not_declared_is_inferred():
	# canonical field used but not declared: added from the registry
	decl = declared(header={})
	used = blank_used()
	used["header"] = {"invoice_number": {"type": None, "strong": False}}
	with_required(used)
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert errors == [], errors
	entry = schema["header"]["invoice_number"]
	assert entry["origin"] == "canonical" and entry.get("inferred")
	assert any("invoice_number" in warning and "not declared" in warning for warning in warnings)
	print("OK used not declared -> inferred from the canonical registry")


def test_used_extension_is_inferred_with_guessed_type():
	decl = declared(header={})
	used = blank_used()
	with_required(used)
	used["extra"] = {"portal_discount_rate": {"type": None, "strong": False}}
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert errors == [], errors
	entry = schema["extra"]["portal_discount_rate"]
	assert entry["origin"] == "inferred" and entry["type"] == "percent"
	print("OK inferred extension type guessed from the name suffix")


def test_type_conflict_is_an_error():
	# declared money, used as date -> error
	decl = declared(totals={"total_ttc": {"label": "Total TTC", "type": "money"}})
	used = blank_used()
	used["totals"] = {"total_ttc": {"type": "date", "strong": True}}
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert any("declared as money but used as date" in error for error in errors), errors
	print("OK type conflict -> error")


def test_numeric_family_does_not_conflict():
	# number arithmetic on a money field is one numeric family: no conflict
	decl = declared(lines={"unit_price": {"label": "Unit Price", "type": "money"}})
	used = blank_used()
	used["lines"] = {"unit_price": {"type": "number", "strong": True}}
	with_required(used)
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert errors == [], errors
	assert schema["lines"]["unit_price"]["type"] == "money"
	print("OK numeric family compatible")


def test_required_canonical_missing_is_an_error():
	decl = declared(header={})
	used = blank_used()
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	for required in ("invoice_number", "invoice_date", "designation", "total_ttc"):
		assert any(required in error and "neither declared nor used" in error for error in errors), errors
	print("OK required canonical fields missing -> errors")


def test_extension_rejects_bad_keys_types_and_labels():
	decl = declared(header={"Invoice-Number": {"label": "X", "type": "text"}})
	used = blank_used()
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert any("snake_case" in error for error in errors)
	decl = declared(header={"custom_ref": {"label": "Custom Ref", "type": "blob"}})
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert any("not allowed" in error for error in errors)
	decl = declared(header={"custom_ref": {"label": "", "type": "text"}})
	schema, errors, warnings = reconcile(CANONICAL, decl, used)
	assert any("label is required" in error for error in errors)
	print("OK extension validation (key shape, allowed types, labels)")


def test_dynamic_metadata_from_real_sources():
	# steps 1-2 on real sources: the Python fixture declares MORE fields and
	# the AST inference finds the used keys independently
	fixtures = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
	with open(os.path.join(fixtures, "rich_template.py"), encoding="utf-8") as handle:
		source = handle.read()
	declared, meta_errors = read_python_metadata(source)
	assert meta_errors == [], meta_errors
	assert declared["document_type"] == "Facture Achat"
	assert "client_portal_ref" in declared["header"]
	assert declared["lines"]["designation"]["type"] == "text"
	used = infer_python(source)
	assert used["header"].get("invoice_number"), used
	assert used["lines"].get("designation"), used
	assert used["totals"].get("total_ttc"), used
	assert used["extra"].get("client_portal_ref"), used
	schema, errors, warnings = reconcile(CANONICAL, declared, used)
	assert errors == [], errors
	# total_ht is declared but never used (the template writes a SUM formula)
	assert "total_ht" not in schema["totals"]
	assert "client_portal_ref" in schema["extra"]
	print("OK dynamic metadata from the rich Python fixture")


def main():
	for name, function in sorted(globals().items()):
		if name.startswith("test_") and callable(function):
			function()
	print("\nALL RECONCILE TESTS PASSED")


if __name__ == "__main__":
	main()
