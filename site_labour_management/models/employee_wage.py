from odoo import api, fields, models


class SiteLabourEmployeeWage(models.Model):
    _name = "site.labour.employee.wage"
    _description = "Site Labour Employee Wage"
    _order = "effective_date desc, id desc"

    employee_id = fields.Many2one("hr.employee", required=True)
    wage_rate = fields.Float(required=True)
    effective_date = fields.Date(required=True, default=fields.Date.context_today)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "employee_effective_unique",
            "unique(employee_id, effective_date)",
            "A wage master already exists for this employee on the same effective date.",
        )
    ]

    @api.model
    def get_latest_rate(self, employee, on_date=False):
        on_date = on_date or fields.Date.context_today(self)
        rec = self.search(
            [
                ("employee_id", "=", employee.id),
                ("effective_date", "<=", on_date),
                ("active", "=", True),
            ],
            order="effective_date desc, id desc",
            limit=1,
        )
        return rec.wage_rate if rec else 0.0
