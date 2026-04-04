from odoo import api, fields, models
from odoo.exceptions import UserError


class SiteLabourPayment(models.Model):
    _name = "site.labour.payment"
    _description = "Site Labour Payment Voucher"
    _order = "payment_date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    payment_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one("account.journal", required=True, domain=[("type", "in", ["bank", "cash"])])
    line_ids = fields.One2many("site.labour.payment.line", "payment_id")
    total_amount = fields.Monetary(compute="_compute_total", store=True, currency_field="currency_id")
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection([("draft", "Draft"), ("posted", "Posted")], default="draft", tracking=True)
    remarks = fields.Char()
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id.id, required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("site.labour.payment") or "New"
        return super().create(vals_list)

    @api.depends("line_ids.amount")
    def _compute_total(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped("amount"))

    def action_post(self):
        expense_account_id = int(self.env["ir.config_parameter"].sudo().get_param("site_labour_management.expense_account_id", 0))
        if not expense_account_id:
            raise UserError("Please configure Labour Expense Account in settings.")

        for rec in self:
            if rec.move_id:
                rec.state = "posted"
                continue
            if not rec.line_ids:
                raise UserError("Add at least one payment line.")
            if rec.total_amount <= 0:
                raise UserError("Total payment amount must be greater than zero.")
            if not rec.journal_id.default_account_id:
                raise UserError("Selected journal must have a default account.")

            line_vals = []
            for line in rec.line_ids:
                line_vals.append(
                    (0, 0, {"name": f"Labour Payment - {line.partner_id.display_name}", "account_id": expense_account_id, "debit": line.amount, "credit": 0.0})
                )
            line_vals.append(
                (0, 0, {"name": f"Labour Payment Voucher {rec.name}", "account_id": rec.journal_id.default_account_id.id, "debit": 0.0, "credit": rec.total_amount})
            )

            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": rec.payment_date,
                    "journal_id": rec.journal_id.id,
                    "ref": rec.name,
                    "line_ids": line_vals,
                }
            )
            move.action_post()
            rec.write({"move_id": move.id, "state": "posted"})


class SiteLabourPaymentLine(models.Model):
    _name = "site.labour.payment.line"
    _description = "Site Labour Payment Voucher Line"

    payment_id = fields.Many2one("site.labour.payment", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", required=True, domain=[("is_team_leader", "=", True)])
    amount = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="payment_id.currency_id", store=True)
