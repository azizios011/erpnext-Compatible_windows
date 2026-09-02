# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import base64
import json

import frappe
import requests
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils import money_in_words


class FactureVente(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		total_ht = 0.0
		for row in self.items:
			row.amount = flt(row.qty) * flt(row.rate)
			total_ht += flt(row.amount)

		total_taxes = 0.0
		for tax in self.taxes:
			total_taxes += flt(tax.tax_amount)

		self.total_ht = total_ht
		self.total_taxes_and_charges = total_taxes
		self.grand_total = total_ht + total_taxes

		if self.grand_total and self.company:
			company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
			self.in_words = money_in_words(self.grand_total, company_currency)


EXTRACTION_PROMPT = """You are extracting structured data from a Tunisian sales invoice (facture de vente).
Return ONLY a single JSON object, with no markdown formatting, no code fences, and no commentary before or after it.

The JSON object must exactly match this shape:
{
  "customer_name": "string or null",
  "tax_id": "string or null (matricule fiscal of the client, exactly as printed)",
  "posting_date": "string or null (invoice date, formatted as YYYY-MM-DD)",
  "reference_number": "string or null (the invoice number as printed, e.g. Facture N)",
  "items": [
    {"description": "string", "qty": number, "uom": "string or null", "rate": number}
  ],
  "taxes": [
    {"charge_type": "TVA" or "Fodec" or "Timbre Fiscal" or "Autre", "rate": number or null, "base_amount": number or null, "tax_amount": number}
  ]
}

Rules:
- qty and rate are the quantity and unit price (HT) of each line item.
- Include one taxes row per distinct TVA rate present, plus a row for Fodec if present, plus a row for Timbre Fiscal if present.
- Use numbers (not strings) for qty, rate, base_amount, tax_amount, and rate percentages.
- If a value is not present on the invoice, use null.
- Do not compute or include any total fields - only items and taxes."""


@frappe.whitelist()
def extract_invoice_data(attachment):
	if not attachment:
		return {"success": False, "error": "No attachment provided."}

	settings = frappe.get_single("Facturation Settings")
	api_key = settings.get_password("anthropic_api_key")
	if not api_key:
		return {
			"success": False,
			"error": "No Anthropic API key configured. Set one in Facturation Settings.",
		}

	model = settings.anthropic_model or "claude-sonnet-4-5"

	try:
		file_doc = frappe.get_doc("File", {"file_url": attachment})
		file_path = file_doc.get_full_path()
	except Exception:
		return {"success": False, "error": "Could not locate the attached file."}

	ext = file_path.lower().rsplit(".", 1)[-1]
	if ext == "pdf":
		media_type = "application/pdf"
		block_type = "document"
	elif ext in ("jpg", "jpeg"):
		media_type = "image/jpeg"
		block_type = "image"
	elif ext == "png":
		media_type = "image/png"
		block_type = "image"
	else:
		return {"success": False, "error": f"Unsupported attachment type: .{ext}"}

	try:
		with open(file_path, "rb") as f:
			encoded = base64.b64encode(f.read()).decode("utf-8")
	except Exception as e:
		return {"success": False, "error": f"Could not read the attached file: {e}"}

	try:
		response = requests.post(
			"https://api.anthropic.com/v1/messages",
			headers={
				"x-api-key": api_key,
				"anthropic-version": "2023-06-01",
				"content-type": "application/json",
			},
			json={
				"model": model,
				"max_tokens": 2000,
				"messages": [
					{
						"role": "user",
						"content": [
							{
								"type": block_type,
								"source": {"type": "base64", "media_type": media_type, "data": encoded},
							},
							{"type": "text", "text": EXTRACTION_PROMPT},
						],
					}
				],
			},
			timeout=60,
		)
		response.raise_for_status()
	except requests.exceptions.RequestException as e:
		return {"success": False, "error": f"Anthropic API request failed: {e}"}

	try:
		result = response.json()
		text = "".join(
			block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
		)
		cleaned = text.strip()
		if cleaned.startswith("```"):
			cleaned = cleaned.strip("`")
			if cleaned.lower().startswith("json"):
				cleaned = cleaned[4:]
			cleaned = cleaned.strip()
		extracted = json.loads(cleaned)
	except Exception as e:
		return {"success": False, "error": f"Could not parse the extraction response: {e}"}

	return {"success": True, "data": extracted}
