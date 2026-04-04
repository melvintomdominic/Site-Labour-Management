from odoo import fields, models


class SiteLabourCategory(models.Model):
    _name = "site.labour.category"
    _description = "Labour Category"

    name = fields.Char(required=True)
    default_wage = fields.Monetary(required=True, currency_field="currency_id")
    ot_rate = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )
    active = fields.Boolean(default=True)
