# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""The Facture Achat validator: the canonical registry of the purchase
invoice and nothing else. Field names are the fixed variable names the
extraction and the templates share; everything outside the registry is an
extension field served from data.extra."""

from erpnext.custom_modules.facturation.template_validators.base import BaseDocumentValidator
from erpnext.custom_modules.facturation.template_validators.registry import register


@register("Facture Achat")
class FactureAchatValidator(BaseDocumentValidator):
	DOCUMENT_TYPE = "Facture Achat"
	CANONICAL = {
		"header": {
			"invoice_number": {"label": "Invoice Number", "type": "text", "required": True},
			"invoice_date": {"label": "Invoice Date", "type": "date", "required": True},
			"due_date": {"label": "Due Date", "type": "date"},
			"order_number": {"label": "Order Number", "type": "text"},
			"delivery_number": {"label": "Delivery Number", "type": "text"},
			"payment_method": {"label": "Payment Method", "type": "text"},
			"currency": {"label": "Currency", "type": "text"},
			"supplier_name": {"label": "Supplier Name", "type": "text"},
			"supplier_tax_id": {"label": "Supplier Tax ID", "type": "text"},
			"supplier_address": {"label": "Supplier Address", "type": "text"},
			"client_name": {"label": "Client Name", "type": "text"},
			"client_code": {"label": "Client Code", "type": "text"},
			"client_address": {"label": "Client Address", "type": "text"},
			"client_tax_id": {"label": "Client Tax ID", "type": "text"},
		},
		"lines": {
			"code": {"label": "Code", "type": "text"},
			"designation": {"label": "Designation", "type": "text", "required": True},
			"quantity": {"label": "Quantity", "type": "number"},
			"unit": {"label": "Unit", "type": "text"},
			"unit_price": {"label": "Unit Price", "type": "money"},
			"discount_percent": {"label": "Discount Percent", "type": "percent"},
			"tva_rate": {"label": "TVA Rate", "type": "percent"},
			"amount_ht": {"label": "Amount HT", "type": "money"},
			"packages_count": {"label": "Packages Count", "type": "number"},
		},
		"totals": {
			"total_ht": {"label": "Total HT", "type": "money"},
			"discount_total": {"label": "Discount Total", "type": "money"},
			"net_ht": {"label": "Net HT", "type": "money"},
			"tva_total": {"label": "TVA Total", "type": "money"},
			"tva_by_rate": {
				"label": "TVA By Rate",
				"type": "list",
				"items": {"rate": "percent", "base": "money", "amount": "money"},
			},
			"timbre": {"label": "Timbre", "type": "money"},
			"total_ttc": {"label": "Total TTC", "type": "money", "required": True},
			"amount_in_words": {"label": "Amount In Words", "type": "text"},
		},
	}
