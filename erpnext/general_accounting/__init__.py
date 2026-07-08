"""General Accounting module alias.

Display name is "General Accounting" (see modules.txt). Implementation files
live under erpnext.tunisian_accounting; this package re-exports that tree so
Frappe can resolve erpnext.general_accounting.* imports and DocType sync paths.
"""

from pathlib import Path

_impl = Path(__file__).resolve().parent.parent / "tunisian_accounting"
__path__ = [str(_impl)]

# Frappe reads __file__ for sync paths — point at the implementation package root.
__file__ = str(_impl / "__init__.py")
