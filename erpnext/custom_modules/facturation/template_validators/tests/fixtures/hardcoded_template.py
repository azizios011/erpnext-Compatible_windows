# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Python fixture template that VIOLATES the contract: values copied from a
source document (a fixed invoice number, a fixed date and a fixed amount)
are written into every output, so the hard-coded data detector must fail it
even though the metadata and the field usage follow the contract."""

DOCUMENT_TYPE = "Facture Achat"
TEMPLATE_NAME = "Hardcoded Fixture Template"
PAGE = {"size": "A4", "orientation": "portrait"}
HEADER_FIELDS = {
	"invoice_number": {"label": "Invoice Number", "type": "text"},
	"invoice_date": {"label": "Invoice Date", "type": "date"},
}
LINE_COLUMNS = [
	{"key": "designation", "label": "Designation", "type": "text"},
]
TOTAL_FIELDS = {
	"total_ttc": {"label": "Total TTC", "type": "money"},
}
EXTRA_FIELDS = {}
LANGUAGES = ["fr"]

import openpyxl


def build(data: dict, output_path: str) -> str:
	workbook = openpyxl.Workbook()
	sheet = workbook.active
	sheet.title = "Facture"

	sheet["A1"] = "Invoice Number"
	sheet["B1"] = data["header"].get("invoice_number")
	# copied from the source document: identical in every output
	sheet["B2"] = "FA-2026-0142"
	sheet["A3"] = "Invoice Date"
	sheet["B3"] = "2026-03-15"
	sheet["B4"] = 1234.567

	row = 6
	for line in data["lines"]:
		sheet.cell(row=row, column=1, value=line["designation"])
		row += 1

	sheet.cell(row=row, column=1, value="Total TTC")
	sheet.cell(row=row, column=2, value=data["totals"]["total_ttc"])

	workbook.save(output_path)
	return output_path
