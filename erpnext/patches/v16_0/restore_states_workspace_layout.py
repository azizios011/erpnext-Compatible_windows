import frappe

from erpnext.general_accounting.after_migrate import apply_general_accounting_desktop_layout


def execute():
	apply_general_accounting_desktop_layout()
