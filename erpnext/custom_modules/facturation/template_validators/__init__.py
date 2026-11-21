# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Per-doctype template validators for the Facturation print formats.

Importing the package registers the validators (one module per Facturation
doctype). frappe-free by design: base.py and the validators run inside the
sandboxed subprocess too."""

from erpnext.custom_modules.facturation.template_validators.base import (
	BaseDocumentValidator,
	hash_editor_contents,
)
from erpnext.custom_modules.facturation.template_validators.registry import (
	get_validator,
	register,
	registered_document_types,
)

# the import registers FactureAchatValidator as a side effect
from erpnext.custom_modules.facturation.template_validators import facture_achat  # noqa: F401,E402
