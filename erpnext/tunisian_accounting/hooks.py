app_name = "erpnext"
app_title = "Tunisian Accounting"
app_publisher = "Your Company"
app_description = "Tunisian Accounting Module - SYSCOHADA/PCG Chart of Accounts"
app_version = "0.0.1"

fixtures = ["Desktop Icon"]

# Generates tn_plan_comptable_avec_code.json in verified/ from the data/ class files.
# Runs once automatically when the app is installed via: bench install-app erpnext
after_install = "erpnext.tunisian_accounting.setup.build_coa_json"
