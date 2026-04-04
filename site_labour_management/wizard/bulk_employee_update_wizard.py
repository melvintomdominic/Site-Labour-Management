from odoo import fields, models


class SiteLabourBulkEmployeeUpdateWizard(models.TransientModel):
    _name = "site.labour.bulk.employee.update.wizard"
    _description = "Bulk Employee Wage/OT Update by Analytic"

    analytic_account_id = fields.Many2one("account.analytic.account", required=True)
    work_date = fields.Date(required=True, default=fields.Date.context_today)
    employee_ids = fields.Many2many("hr.employee", domain="[('department_id.name', 'ilike', 'Operations')]")
    wage_rate = fields.Float(required=True)
    ot_hours = fields.Float(default=0.0)

    def action_apply(self):
        sheets = self.env["site.labour.sheet"].search(
            [
                ("date", "=", self.work_date),
                ("analytic_account_id", "=", self.analytic_account_id.id),
            ]
        )
        lines = sheets.mapped("individual_line_ids")
        if self.employee_ids:
            lines = lines.filtered(lambda l: l.employee_id in self.employee_ids)
        lines.write({"daily_wage_rate": self.wage_rate, "wage": self.wage_rate, "worked_hours": 9 + self.ot_hours})
        return {"type": "ir.actions.act_window_close"}
