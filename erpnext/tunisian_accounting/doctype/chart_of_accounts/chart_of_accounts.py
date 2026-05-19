# erpnext/tunisian_accounting/doctype/chart_of_accounts/chart_of_accounts.py

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class ChartofAccounts(NestedSet):
    nsm_parent_field = "parent_chart_of_accounts"

    def validate(self):
        self.validate_group_or_leaf()

    def validate_group_or_leaf(self):
        """A group account cannot have account_type or sens — those belong to leaf accounts."""
        if self.is_group:
            if self.account_type:
                frappe.msgprint(
                    _("Account Type is not applicable for group accounts."),
                    alert=True,
                )

    def on_update(self):
        super().on_update()

    def before_rename(self, old, new, merge=False):
        # Prevent renaming if the account is synced to ERPNext Account
        if frappe.db.exists("Account", {"custom_coa_ref": old}):
            frappe.throw(
                _(
                    "Cannot rename account {0} — it has already been synced to ERPNext accounts. "
                    "Rename the synced Account first."
                ).format(old)
            )


@frappe.whitelist()
def get_children(doctype, parent=None, is_root=False):
    """
    Returns direct children for the tree view.
    Called by Frappe's tree widget via frappe.treeview_settings.
    """
    filters = [["Chart of Accounts", "disabled", "=", 0]]

    if is_root or not parent:
        filters.append(["Chart of Accounts", "parent_chart_of_accounts", "=", ""])
    else:
        filters.append(["Chart of Accounts", "parent_chart_of_accounts", "=", parent])

    return frappe.get_list(
        "Chart of Accounts",
        fields=[
            "name as value",
            "account_name as title",
            "account_number",
            "root_type",
            "account_type",
            "sens",
            "is_group as expandable",
            "parent_chart_of_accounts as parent",
        ],
        filters=filters,
        order_by="account_number asc",
    )
