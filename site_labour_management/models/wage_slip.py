from odoo import api, fields, models


class SiteLabourWageSlip(models.Model):
    _name = "site.labour.wage.slip"
    _description = "Site Labour Wage Slip"
    _order = "date_from desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    partner_id = fields.Many2one("res.partner", required=True)
    date_from = fields.Date(required=True)
    date_to = fields.Date(required=True)
    weekly_bill_id = fields.Many2one("site.labour.weekly.bill")
    sheet_ids = fields.Many2many("site.labour.sheet")
    total_amount = fields.Monetary(compute="_compute_total", store=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )

    @api.depends("weekly_bill_id.amount_total", "sheet_ids.total_amount")
    def _compute_total(self):
        for rec in self:
            rec.total_amount = rec.weekly_bill_id.amount_total or sum(rec.sheet_ids.mapped("total_amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("site.labour.wage.slip") or "New"
        return super().create(vals_list)
