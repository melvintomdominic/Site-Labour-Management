from odoo import fields, models


class SiteLabourEmployeeWage(models.Model):
    _name = "site.labour.employee.wage"
    _description = "Site Labour Employee Wage"
    _order = "effective_date desc, id desc"

    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        domain=[("company_type", "=", "person")],
        string="Employee / Labour",
    )
    wage_rate = fields.Float(required=True)
    effective_date = fields.Date(required=True, default=fields.Date.context_today)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "partner_effective_unique",
            "unique(partner_id, effective_date)",
            "A wage entry already exists for this partner on the same effective date.",
        )
    ]
