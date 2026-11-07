# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import base64
import json

import frappe
import requests

from erpnext.custom_modules.facturation.facturation_base import FacturationDocument


class FactureVente(FacturationDocument):
	journal_code = "VT"


EXTRACTION_PROMPT = """You are extracting structured data from a Tunisian sales invoice (facture de vente).
Return ONLY a single JSON object, with no markdown formatting, no code fences, and no commentary before or after it.

The JSON object must exactly match this shape:
{
  "posting_date": "string or null (invoice date, formatted as YYYY-MM-DD)",
  "reference_number": "string or null (the invoice number as printed, e.g. Facture N)"
}

Rules:
- The form only carries these two fields plus the attachment; the customer is
  picked manually on the Link field, so no party data is extracted.
- If a value is not present on the invoice, use null.
- Do not compute or include any other fields."""


def _get_settings():
	settings = frappe.get_single("AI Settings")
	api_key = settings.get_password("api_key")
	if not api_key:
		frappe.throw("No API key configured. Set one in AI Settings.")
	if not settings.model:
		frappe.throw("No model selected in AI Settings. Click 'Refresh Models List' and choose one.")
	return settings.provider, api_key, settings.model


def _load_file_bytes(attachment):
	file_doc = frappe.get_doc("File", {"file_url": attachment})
	file_path = file_doc.get_full_path()
	with open(file_path, "rb") as f:
		content = f.read()
	ext = file_path.lower().rsplit(".", 1)[-1]
	return content, ext


def _pdf_first_page_to_png(pdf_bytes):
	import fitz  # PyMuPDF

	doc = fitz.open(stream=pdf_bytes, filetype="pdf")
	page = doc.load_page(0)
	pix = page.get_pixmap(dpi=200)
	return pix.tobytes("png")


def _call_anthropic(api_key, model, content, ext):
	if ext == "pdf":
		media_type, block_type = "application/pdf", "document"
	elif ext in ("jpg", "jpeg"):
		media_type, block_type = "image/jpeg", "image"
	elif ext == "png":
		media_type, block_type = "image/png", "image"
	else:
		frappe.throw(f"Unsupported attachment type: .{ext}")

	encoded = base64.b64encode(content).decode("utf-8")
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
	result = response.json()
	return "".join(
		block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
	)


def _call_openrouter(api_key, model, content, ext):
	if ext == "pdf":
		content = _pdf_first_page_to_png(content)
		media_type = "image/png"
	elif ext in ("jpg", "jpeg"):
		media_type = "image/jpeg"
	elif ext == "png":
		media_type = "image/png"
	else:
		frappe.throw(f"Unsupported attachment type: .{ext}")

	encoded = base64.b64encode(content).decode("utf-8")
	response = requests.post(
		"https://openrouter.ai/api/v1/chat/completions",
		headers={
			"Authorization": f"Bearer {api_key}",
			"content-type": "application/json",
		},
		json={
			"model": model,
			"max_tokens": 2000,
			"messages": [
				{
					"role": "user",
					"content": [
						{"type": "text", "text": EXTRACTION_PROMPT},
						{
							"type": "image_url",
							"image_url": {"url": f"data:{media_type};base64,{encoded}"},
						},
					],
				}
			],
		},
		timeout=60,
	)
	response.raise_for_status()
	result = response.json()
	choices = result.get("choices", [])
	if not choices:
		frappe.throw("No response from OpenRouter.")
	return choices[0]["message"]["content"]


@frappe.whitelist()
def extract_invoice_data(attachment: str) -> dict:
	if not attachment:
		return {"success": False, "error": "No attachment provided."}

	try:
		provider, api_key, model = _get_settings()
	except Exception as e:
		return {"success": False, "error": str(e)}

	try:
		content, ext = _load_file_bytes(attachment)
	except Exception as e:
		return {"success": False, "error": f"Could not read the attached file: {e}"}

	try:
		if provider == "Anthropic":
			text = _call_anthropic(api_key, model, content, ext)
		elif provider == "OpenRouter":
			text = _call_openrouter(api_key, model, content, ext)
		else:
			return {"success": False, "error": f"Unknown provider: {provider}"}
	except requests.exceptions.RequestException as e:
		return {"success": False, "error": f"API request failed: {e}"}
	except Exception as e:
		return {"success": False, "error": str(e)}

	try:
		cleaned = text.strip()
		if cleaned.startswith("```"):
			cleaned = cleaned.strip("`")
			if cleaned.lower().startswith("json"):
				cleaned = cleaned[4:]
			cleaned = cleaned.strip()
		extracted = json.loads(cleaned)
	except Exception as e:
		return {"success": False, "error": f"Could not parse the extraction response: {e}"}

	# the upload form carries only the base fields: drop anything else the
	# model may have produced instead of failing
	extracted = {
		key: extracted[key] for key in ("posting_date", "reference_number") if key in extracted
	}

	return {"success": True, "data": extracted}
