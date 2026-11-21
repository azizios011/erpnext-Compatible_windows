# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Tests of the hard-coded data detector (unit) and end-to-end validation
of the three fixture templates through the sandboxed subprocess: the rich
Python template passes (with the declared-but-unused warning), the minimal
HTML/CSS template passes with the inferred-date warning and the hard-coded
template must fail. Runs with pytest or plain python; needs a python with
openpyxl and jinja2 (the bench env) because the sandbox uses sys.executable."""

import os
import sys

sys.path.insert(
	0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))
)

from erpnext.custom_modules.facturation.template_validators.base import (  # noqa: E402
	detect_hardcoded_data,
	extract_output_text,
)
from erpnext.custom_modules.facturation.template_validators.registry import (  # noqa: E402
	get_validator,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
VALIDATOR = get_validator("Facture Achat")


def _read(name):
	with open(os.path.join(FIXTURES, name), encoding="utf-8") as handle:
		return handle.read()


def test_detector_flags_copied_values():
	# data-like text present IDENTICALLY in both outputs = copied from the
	# source document; the dataset's own values differ and never match
	text_a = "Invoice FA-2026-0142\n2026-03-15\n1234.567\nTotal TTC\nDesignation A-L001\n2026-01-15"
	text_b = "Invoice FA-2026-0142\n2026-03-15\n1234.567\nTotal TTC\nDesignation B-L001\n2026-02-18"
	flagged = detect_hardcoded_data(text_a, text_b)
	for token in ("FA-2026-0142", "2026-03-15", "1234.567"):
		assert token in flagged, flagged
	# plain labels and static branding never match a data pattern
	assert "Total TTC" not in flagged
	assert "Designation" not in flagged
	# the dataset's own varying values are not identical -> not flagged
	assert "2026-01-15" not in flagged and "2026-02-18" not in flagged
	print("OK detector flags the copied values only")


def test_detector_ignores_varying_data():
	flagged = detect_hardcoded_data("FA-2026-0001 111.111", "FA-2026-0002 222.222")
	assert flagged == [], flagged
	print("OK detector ignores values that differ between the datasets")


def test_rich_python_template_passes():
	source = _read("rich_template.py")
	result = VALIDATOR.validate(mode="Python", files={"python": source}, timeout=60)
	assert result["status"] in ("Passed", "Passed With Warnings"), result["log"]
	# total_ht is declared but never used (a SUM formula covers the lines)
	assert "total_ht" not in result["schema"]["totals"]
	assert "client_portal_ref" in result["schema"]["extra"]
	assert any("total_ht" in line and "dropped" in line for line in result["log"])
	print(f"OK rich python fixture: {result['status']}")


def test_minimal_html_template_passes_with_warnings():
	files = {"html": _read("minimal_template.py").split('HTML_SOURCE = """')[1].split('"""')[0],
	         "css": _read("minimal_template.py").split('CSS_SOURCE = """')[1].split('"""')[0]}
	result = VALIDATOR.validate(mode="HTML/CSS", files=files, timeout=60)
	assert result["status"] == "Passed With Warnings", result["log"]
	# the invoice date is used but not declared: inferred, canonical
	entry = result["schema"]["header"]["invoice_date"]
	assert entry["origin"] == "canonical" and entry.get("inferred")
	assert result["schema"]["lines"]["designation"]["origin"] == "canonical"
	print("OK minimal html fixture: Passed With Warnings (inferred date)")


def test_hardcoded_template_fails():
	source = _read("hardcoded_template.py")
	result = VALIDATOR.validate(mode="Python", files={"python": source}, timeout=60)
	assert result["status"] == "Failed", result["log"]
	flagged = [line for line in result["log"] if "looks copied from the source document" in line]
	assert flagged, result["log"]
	assert any("FA-2026-0142" in line for line in flagged)
	assert any("2026-03-15" in line for line in flagged)
	assert any("1234.567" in line for line in flagged)
	print(f"OK hardcoded fixture: Failed ({len(flagged)} copied values)")


def test_sample_datasets_shape():
	schema = {
		"header": {"invoice_number": {"label": "Invoice Number", "type": "text", "required": True, "origin": "canonical"}},
		"lines": {"designation": {"label": "Designation", "type": "text", "required": True, "origin": "canonical"}},
		"totals": {"total_ttc": {"label": "Total TTC", "type": "money", "required": True, "origin": "canonical"}},
		"extra": {},
	}
	datasets = VALIDATOR.sample_datasets(schema)
	assert [entry["tag"] for entry in datasets] == ["A", "B"]
	assert len(datasets[0]["data"]["lines"]) == 1
	assert len(datasets[1]["data"]["lines"]) == 25
	assert datasets[0]["data"]["totals"]["total_ttc"] != datasets[1]["data"]["totals"]["total_ttc"]
	assert datasets[0]["data"]["lines"][0]["designation"] != datasets[1]["data"]["lines"][0]["designation"]
	print("OK sample datasets: 1 line vs 25 lines, distinctive tokens")


def test_describe_contract_is_facts_only():
	contract = VALIDATOR.describe_contract()
	for fact in ("invoice_number", "total_ttc", "money (3 decimals, TND)", "date_fr", "Forbidden"):
		assert fact in contract, fact
	assert "FACTURE_ACHAT" not in contract  # a filename, not a fact
	print("OK describe_contract: registry facts")


def test_output_text_extraction_roundtrip():
	# the html text extraction drops the tags but keeps every value
	files = {
		"html": _read("minimal_template.py").split('HTML_SOURCE = """')[1].split('"""')[0],
		"css": _read("minimal_template.py").split('CSS_SOURCE = """')[1].split('"""')[0],
	}
	datasets = VALIDATOR.sample_datasets({
		"header": {"invoice_number": {"label": "Invoice Number", "type": "text", "required": True, "origin": "canonical"}},
		"lines": {"designation": {"label": "Designation", "type": "text", "required": True, "origin": "canonical"}},
		"totals": {"total_ttc": {"label": "Total TTC", "type": "money", "required": True, "origin": "canonical"}},
		"extra": {},
	})
	entry = datasets[0]
	import tempfile

	with tempfile.TemporaryDirectory() as tmp:
		paths = VALIDATOR.generate(mode="HTML/CSS", files=files, data=entry["data"], out_dir=tmp, timeout=60)
		text = extract_output_text(paths)
	assert entry["data"]["header"]["invoice_number"] in text
	assert entry["data"]["lines"][0]["designation"] in text
	print("OK html output carries every rendered value")


def main():
	for name, function in sorted(globals().items()):
		if name.startswith("test_") and callable(function):
			function()
	print("\nALL DETECTOR AND FIXTURE TESTS PASSED")


if __name__ == "__main__":
	main()
