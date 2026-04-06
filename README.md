# Site Labour Management

Odoo 18 module for site labour attendance, wage calculation, approval flow, and automatic vendor billing.

## Attendance module structure
### 1) Labour Sheet (`site.labour.sheet`)
Primary daily attendance document.

Main fields:
- Date
- Project (`project_id`)
- Supervisor (`supervisor_id`)
- State (`draft` / `submitted` / `approved`)
- Labour Lines (`labour_line_ids`)
- Total Amount
- Photo Proof (`photo`)

### 2) Labour Line (`site.labour.line`)
Child attendance rows.

Main fields:
- Labour
- Present
- Days
- Rate
- Total (`days * rate` when present)

## Workflow
Draft -> Submitted -> Approved

On **Approve**:
- Validates attendance lines + photo proof
- Creates and posts vendor bill automatically
- Uses Supervisor as vendor partner

## Implemented features
- Daily site labour tracking and line-level wage math.
- Team and individual attendance support.
- Photo validation before submission.
- Automatic vendor bill creation on approval.
- Daily and weekly bill models for billing operations.
- Wage records:
  - Daily Wage Slips
  - Wage Slips
  - Employee Wage master list (`site.labour.employee.wage`)
- Payment vouchers (`site.labour.payment`).
- Twilio/WhatsApp reminders and notifications.

## Not implemented yet
- Full HR/employee integration (bulk employee wage update based on `hr.employee`) is **not implemented**.

## Security groups
- **Site Labour Supervisor**: operational entry (attendance and operations)
- **Site Labour Admin**: full control and master/config management
- **Site Labour Billing**: billing and financial operations

## WhatsApp / Twilio settings
Configure in module settings:
- Twilio Account SID
- Twilio Auth Token
- Twilio WhatsApp sender number
- Labour Expense Account
- OT trigger hours
- Default billing frequency

## Deployment / upgrade
1. Restart Odoo service
2. Upgrade module:
   - UI: Apps -> Upgrade **Site Labour Management**
   - CLI: `odoo-bin -d <db_name> -u site_labour_management --stop-after-init`
3. Hard refresh browser assets
