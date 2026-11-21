# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Registry of the per-doctype template validators. Every Facturation
doctype that grows templates gets its own module with its own canonical
registry, registered here; nothing doctype-specific lives in base.py."""

_VALIDATORS: dict = {}


def register(document_type: str):
	"""Class decorator: register(document_type) above a BaseDocumentValidator
	subclass makes it the validator of that Facturation doctype."""

	def decorator(cls):
		instance = cls()
		instance.DOCUMENT_TYPE = document_type
		_VALIDATORS[document_type] = instance
		return cls

	return decorator


def get_validator(document_type: str):
	"""The validator of a Facturation doctype, or None when no validator
	exists for it yet."""
	return _VALIDATORS.get(document_type or "")


def registered_document_types() -> list:
	return sorted(_VALIDATORS)
