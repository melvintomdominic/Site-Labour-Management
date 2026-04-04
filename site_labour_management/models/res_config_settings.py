from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    labour_expense_account_id = fields.Many2one(
        "account.account",
        string="Labour Expense Account",
        config_parameter="site_labour_management.expense_account_id",
        domain=[("account_type", "=", "expense")],
    )
    default_ot_hours = fields.Float(
        string="Standard OT Trigger Hours",
        default=9.0,
        config_parameter="site_labour_management.default_ot_hours",
    )
    twilio_sid = fields.Char(config_parameter="site_labour_management.twilio_sid")
    twilio_token = fields.Char(config_parameter="site_labour_management.twilio_token")
    twilio_from_number = fields.Char(config_parameter="site_labour_management.twilio_from_number")

    billing_frequency = fields.Selection(
        [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        string="Vendor Bill Posting Frequency",
        default="weekly",
        config_parameter="site_labour_management.billing_frequency",
    )
