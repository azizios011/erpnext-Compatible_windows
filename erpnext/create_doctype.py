import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    doctype_name = "Journals Creations"
    
    if frappe.db.exists("DocType", doctype_name):
        print(f"DocType {doctype_name} already exists.")
        doc = frappe.get_doc("DocType", doctype_name)
    else:
        doc = frappe.new_doc("DocType")
        doc.name = doctype_name
        doc.module = "Tunisian Accounting"
        doc.custom = 0
        doc.istable = 0
        doc.editable_grid = 1
        doc.track_changes = 1
        doc.autoname = "field:template_title"
        doc.naming_rule = "By fieldname"
        
    doc.fields = []
    
    fields = [
        {
            "fieldname": "section_break_1",
            "fieldtype": "Section Break",
        },
        {
            "fieldname": "template_title",
            "fieldtype": "Data",
            "label": "Template Title",
            "reqd": 1,
            "unique": 1,
        },
        {
            "fieldname": "company",
            "fieldtype": "Link",
            "label": "Company",
            "options": "Company",
            "reqd": 1,
            "in_list_view": 1,
            "in_standard_filter": 1,
            "remember_last_selected_value": 1,
        },
        {
            "fieldname": "voucher_type",
            "fieldtype": "Select",
            "label": "Journal Entry Type",
            "options": "Journal Entry\nInter Company Journal Entry\nBank Entry\nCash Entry\nCredit Card Entry\nDebit Note\nCredit Note\nContra Entry\nExcise Entry\nWrite Off Entry\nOpening Entry\nDepreciation Entry\nExchange Rate Revaluation",
            "reqd": 1,
            "in_list_view": 1,
        },
        {
            "fieldname": "is_opening",
            "fieldtype": "Select",
            "label": "Is Opening",
            "options": "No\nYes",
            "default": "No",
        },
        {
            "fieldname": "naming_series",
            "fieldtype": "Select",
            "label": "Series",
            "reqd": 1,
            "set_only_once": 1,
            "no_copy": 1,
            "print_hide": 1,
        },
        {
            "fieldname": "multi_currency",
            "fieldtype": "Check",
            "label": "Multi Currency",
            "default": "0",
        }
    ]
    
    for f in fields:
        doc.append("fields", f)
        
    doc.permissions = [
        {
            "role": "Accounts User",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "report": 1,
            "export": 1,
            "import": 0,
            "share": 1,
            "print": 1,
            "email": 1,
        },
        {
            "role": "Accounts Manager",
            "read": 1,
            "write": 1,
            "create": 1,
            "delete": 1,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "report": 1,
            "export": 1,
            "import": 0,
            "share": 1,
            "print": 1,
            "email": 1,
        },
        {
            "role": "Auditor",
            "read": 1,
            "write": 0,
            "create": 0,
            "delete": 0,
            "submit": 0,
            "cancel": 0,
            "amend": 0,
            "report": 1,
            "export": 1,
            "import": 0,
            "share": 1,
            "print": 1,
            "email": 1,
        }
    ]
    
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("Successfully created Journals Creations DocType")

