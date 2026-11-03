import frappe


def execute():
	"""Drop the Societe DocType once its table is empty.

	The Companies link is gone; Entreprises is the tenant boundary. A site that
	already stored Societe rows keeps the DocType so those rows are not lost.
	"""
	doctype = "Societe"
	if not frappe.db.exists("DocType", doctype):
		return
	if frappe.db.table_exists(doctype) and frappe.db.count(doctype):
		frappe.logger("axeane").info("Societe has rows; leaving the DocType in place")
		return
	try:
		frappe.delete_doc("DocType", doctype, force=1, ignore_missing=True)
	except Exception:
		frappe.log_error(title="Societe cleanup failed", message=frappe.get_traceback())
