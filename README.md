# Site Labour Management

Production-focused Odoo 18 module for site labour operations, project costing, and weekly payable control.

## Features
- Daily labour sheet capture with project + analytic linkage.
- GPS + photo proof validation before submission.
- Team and individual labour entries with OT auto-calculation.
- Approval workflow (`draft -> submitted -> approved`).
- Consolidated vendor billing with configurable posting frequency (daily/weekly/monthly).
- Vendor bill generation into Odoo accounting (`in_invoice`).
- Wage slip records from weekly bills or selected sheets.
- WhatsApp notifications via Twilio on approval/billing/reminders.
- Daily missing-entry and overdue-payment cron reminders.
- Dashboard-ready graph + pivot views for cost analysis.
- Daily wage slips and payment register with labour summary pivot.

## Module path
`site_labour_management`

## Dependencies
- `base`
- `project`
- `account`
- `mail`

## Configuration
Open **Accounting > Settings > Site Labour** and configure:
- Labour Expense Account
- OT Trigger Hours
- Twilio SID / Token / WhatsApp sender number

## Security Roles
- **Site Labour Supervisor**: create/submit sheets.
- **Site Labour Admin**: approval + configuration control.
- **Site Labour Billing**: weekly bill and wage-slip operations.
