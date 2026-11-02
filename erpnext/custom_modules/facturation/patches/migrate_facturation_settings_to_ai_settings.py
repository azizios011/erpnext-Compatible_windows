import frappe
from frappe.utils.password import get_decrypted_password


def execute():
	"""Copy Facturation Settings data into AI Settings (idempotent), then drop
	the old single when the framework allows it.

	The old doctype folder is removed from the app, so on migrate the DocType
	becomes an orphan while its rows (and the encrypted api_key) stay in the
	database — this patch copies what it can and only then deletes it."""
	if not frappe.db.exists("DocType", "AI Settings"):
		# the Axeane Settings module has not synced yet on the first migrate
		# (stale app_modules cache) — leave the old data in place
		frappe.log_error(
			title="Facturation Settings migration skipped",
			message="AI Settings doctype not found; run bench migrate again after the module cache clears.",
		)
		return
	if not frappe.db.exists("DocType", "Facturation Settings"):
		return
	old = frappe.db.get_singles_dict("Facturation Settings") or {}
	if not old:
		return

	ai = frappe.get_doc("AI Settings", "AI Settings")
	if ai.get_password("api_key", raise_exception=False):
		return  # already migrated

	ai.provider = old.get("provider") or ai.provider
	ai.model = old.get("model") or ai.model
	api_key = get_decrypted_password(
		"Facturation Settings", "Facturation Settings", "api_key", raise_exception=False
	) or ""
	if api_key:
		ai.api_key = api_key
	ai.save(ignore_permissions=True)

	try:
		frappe.delete_doc("DocType", "Facturation Settings", force=1, ignore_missing=True)
	except Exception:
		frappe.log_error(
			title="Facturation Settings cleanup failed",
			message=frappe.get_traceback(),
		)
