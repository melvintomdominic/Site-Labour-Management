# Site Labour Management

Production-focused Odoo 18 module for site labour operations, analytic project costing, billing, and payments.

## Features
- Daily labour sheet capture with attendance mode (`team` / `individual`).
- GPS + photo proof validation before submission.
- Team and individual labour entries with OT auto-calculation.
- Approval workflow (`draft -> submitted -> approved`).
- Consolidated vendor billing with configurable posting frequency (daily/weekly/monthly).
- Vendor bill generation into Odoo accounting (`in_invoice`).
- Wage slip records and labour wage payment register.
- WhatsApp notifications via Twilio on approval/billing/reminders.
- Daily missing-entry and overdue-payment cron reminders.
- Graph + pivot views for cost analysis.

## Module path
`site_labour_management`

## Dependencies
- `base`
- `account`
- `mail`

## Configuration
Open **Accounting > Settings > Site Labour** and configure:
- Labour Expense Account
- OT Trigger Hours
- Twilio SID / Token / WhatsApp sender number

## Database-safe deployment
To avoid deployment-time schema errors (for example `UndefinedColumn`), follow this order:

1. Deploy code to server.
2. Restart Odoo service.
3. Upgrade module immediately:
   - UI: Apps -> Update Apps List -> Upgrade **Site Labour Management**
   - CLI: `odoo-bin -d <db_name> -u site_labour_management --stop-after-init`
4. Clear browser cache / reload web assets.

### Safety notes
- This module avoids runtime references to non-core custom `res.partner` columns.
- Partner hierarchy logic uses core fields (`parent_id`) so reads remain safe before/after upgrades.
- If you add new stored fields in future changes, always run `-u site_labour_management` before user traffic.

## Security Roles
- **Site Labour Supervisor**: create/submit sheets.
- **Site Labour Admin**: approval + configuration control.
- **Site Labour Billing**: bill and wage-slip operations.
