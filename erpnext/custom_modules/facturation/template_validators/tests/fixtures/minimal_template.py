# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Minimal HTML/CSS fixture template: only the required canonical fields
plus the invoice date (used but not declared -> inferred), rendered through
the contract filters. Follows the contract."""

HTML_SOURCE = """<script type="application/json" id="template-meta">
{
	"DOCUMENT_TYPE": "Facture Achat",
	"TEMPLATE_NAME": "Minimal Fixture Template",
	"PAGE": {"size": "A4", "orientation": "portrait"},
	"HEADER_FIELDS": {"invoice_number": {"label": "Invoice Number", "type": "text"}},
	"LINE_COLUMNS": [{"key": "designation", "label": "Designation", "type": "text"}],
	"TOTAL_FIELDS": {"total_ttc": {"label": "Total TTC", "type": "money"}},
	"LANGUAGES": ["fr"]
}
</script>
<div class="invoice">
	<p>Invoice {{ header.invoice_number }} of {{ header.invoice_date|date_fr }}</p>
	<ul class="lines">
	{% for line in lines %}
		<li>{{ line.designation }}</li>
	{% endfor %}
	</ul>
	<p>Total TTC {{ totals.total_ttc|money }}</p>
</div>
"""

CSS_SOURCE = """.invoice { font-family: serif; }
.lines li { margin: 2px 0; }
"""
