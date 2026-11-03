import frappe

DOCTYPES = ("Extrait Achat", "Extrait Vente", "Extrait Bancaire")


def execute():
	"""Drop the three Extrait doctypes once each table is empty.

	Relevé is the remaining statement. A site that already stored Extrait rows
	keeps that DocType so those rows are not lost.
	"""
	for doctype in DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.table_exists(doctype) and frappe.db.count(doctype):
			frappe.logger("axeane").info(f"{doctype} has rows; leaving the DocType in place")
			continue
		try:
			frappe.delete_doc("DocType", doctype, force=1, ignore_missing=True)
		except Exception:
			frappe.log_error(title=f"{doctype} cleanup failed", message=frappe.get_traceback())
