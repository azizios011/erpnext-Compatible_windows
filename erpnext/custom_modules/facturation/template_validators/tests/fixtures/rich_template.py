# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Rich Python-mode fixture template: full metadata block (canonical
fields plus one extension per section), the whole data shape used, and a
SUM formula over the line rows. Follows the contract."""

DOCUMENT_TYPE = "Facture Achat"
TEMPLATE_NAME = "Rich Fixture Template"
PAGE = {"size": "A4", "orientation": "portrait"}
HEADER_FIELDS = {
	"invoice_number": {"label": "Invoice Number", "type": "text"},
	"invoice_date": {"label": "Invoice Date", "type": "date"},
	"supplier_name": {"label": "Supplier Name", "type": "text"},
	"client_name": {"label": "Client Name", "type": "text"},
	"client_portal_ref": {"label": "Client Portal Ref", "type": "text"},
}
LINE_COLUMNS = [
	{"key": "designation", "label": "Designation", "type": "text"},
	{"key": "quantity", "label": "Quantity", "type": "number"},
	{"key": "unit_price", "label": "Unit Price", "type": "money"},
	{"key": "amount_ht", "label": "Amount HT", "type": "money"},
]
TOTAL_FIELDS = {
	"total_ht": {"label": "Total HT", "type": "money"},
	"total_ttc": {"label": "Total TTC", "type": "money"},
	"amount_in_words": {"label": "Amount In Words", "type": "text"},
}
EXTRA_FIELDS = {
	"footer_note": {"label": "Footer Note", "type": "text"},
}
LANGUAGES = ["fr"]

import openpyxl


def build(data: dict, output_path: str) -> str:
	workbook = openpyxl.Workbook()
	sheet = workbook.active
	sheet.title = "Facture"

	sheet["A1"] = "Invoice Number"
	sheet["B1"] = data["header"].get("invoice_number")
	sheet["A2"] = "Invoice Date"
	sheet["B2"] = data["header"]["invoice_date"]
	sheet["A3"] = "Supplier"
	sheet["B3"] = data["header"].get("supplier_name")
	sheet["A4"] = "Client"
	sheet["B4"] = data["header"].get("client_name")
	sheet["A5"] = "Portal Ref"
	sheet["B5"] = data["extra"].get("client_portal_ref")
	sheet["A6"] = "Footer"
	sheet["B6"] = data["extra"].get("footer_note")

	header_row = 8
	for column, key in enumerate(("designation", "quantity", "unit_price", "amount_ht"), start=1):
		sheet.cell(row=header_row, column=column, value=key)
	first_row = header_row + 1
	row = header_row
	for line in data["lines"]:
		row += 1
		sheet.cell(row=row, column=1, value=line["designation"])
		sheet.cell(row=row, column=2, value=line["quantity"])
		sheet.cell(row=row, column=3, value=line["unit_price"])
		sheet.cell(row=row, column=4, value=line["amount_ht"])
	last_row = row

	row += 1
	sheet.cell(row=row, column=1, value="Total HT")
	sheet.cell(row=row, column=4, value=f"=SUM(D{first_row}:D{last_row})")
	row += 1
	sheet.cell(row=row, column=1, value="Total TTC")
	sheet.cell(row=row, column=4, value=data["totals"]["total_ttc"])
	row += 1
	sheet.cell(row=row, column=1, value="Amount in words")
	sheet.cell(row=row, column=4, value=data["totals"].get("amount_in_words"))

	workbook.save(output_path)
	return output_path
