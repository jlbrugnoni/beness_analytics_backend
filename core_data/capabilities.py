OPERATIONAL_CAPABILITIES = (
    "can_view_money", "can_upload_data", "can_edit_data", "can_reset_data",
    "can_manage_users", "can_view_admin_logs",
)

FINANCE_CAPABILITIES = (
    "can_view_finance", "can_import_finance", "can_edit_finance",
    "can_reconcile_finance", "can_manage_finance_settings",
    "can_close_finance_periods", "can_export_finance",
    "can_view_finance_bank_accounts", "can_view_sensitive_finance",
)

ALL_CAPABILITIES = OPERATIONAL_CAPABILITIES + FINANCE_CAPABILITIES
