import frappe
from frappe.model.base_document import get_controller

def execute():
    try:
        ctrl = get_controller("Entry of Entries")
        print(f"Controller: {ctrl}")
    except Exception as e:
        import traceback
        traceback.print_exc()
