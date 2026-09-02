# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
import requests
from frappe.model.document import Document


class FacturationSettings(Document):
	pass


@frappe.whitelist()
def get_available_models(provider, api_key):
	if not api_key:
		frappe.throw("Please enter an API key first.")

	if provider == "Anthropic":
		response = requests.get(
			"https://api.anthropic.com/v1/models",
			headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
			timeout=15,
		)
		response.raise_for_status()
		data = response.json()
		return [m["id"] for m in data.get("data", [])]

	if provider == "OpenRouter":
		response = requests.get(
			"https://openrouter.ai/api/v1/models",
			headers={"Authorization": f"Bearer {api_key}"},
			timeout=15,
		)
		response.raise_for_status()
		data = response.json()
		return [m["id"] for m in data.get("data", [])]

	frappe.throw(f"Unknown provider: {provider}")
