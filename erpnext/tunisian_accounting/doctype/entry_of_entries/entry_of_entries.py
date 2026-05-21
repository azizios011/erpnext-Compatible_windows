# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document

class EntryofEntries(Document):
    def validate(self):
        total_debit = sum(row.debit or 0 for row in self.accounting_entries)
        total_credit = sum(row.credit or 0 for row in self.accounting_entries)
        if total_debit != total_credit:
            frappe.throw(f"Debit ({total_debit}) must equal Credit ({total_credit})")
