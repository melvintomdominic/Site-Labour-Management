from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class SiteLabourWeeklyBill(models.Model):
    _name = "site.labour.weekly.bill"
    _description = "Site Labour Weekly Bill"
    _order = "week_start desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    partner_id = fields.Many2one("res.partner", required=True)
    week_start = fields.Date(required=True)
    week_end = fields.Date(required=True)
    sheet_ids = fields.Many2many("site.labour.sheet", string="Labour Sheets")
    line_ids = fields.One2many("site.labour.weekly.bill.line", "weekly_bill_id")
    amount_total = fields.Monetary(compute="_compute_amount_total", store=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("billed", "Billed")], default="draft", tracking=True
    )

    _sql_constraints = [
        (
            "partner_week_unique",
            "unique(partner_id, week_start, week_end)",
            "A weekly consolidated bill already exists for this partner and week.",
        )
    ]

    @api.depends("line_ids.amount")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped("amount"))

    @api.model
    def week_bounds(self, day):
        day = fields.Date.to_date(day)
        week_start = day - timedelta(days=day.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    @api.model
    def get_or_create_for(self, partner, day):
        week_start, week_end = self.week_bounds(day)
        bill = self.search(
            [
                ("partner_id", "=", partner.id),
                ("week_start", "=", week_start),
                ("week_end", "=", week_end),
            ],
            limit=1,
        )
        if not bill:
            bill = self.create(
                {
                    "partner_id": partner.id,
                    "week_start": week_start,
                    "week_end": week_end,
                }
            )
        return bill

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("site.labour.weekly.bill") or "New"
        return super().create(vals_list)

    def action_create_vendor_bill(self):
        expense_account = int(
            self.env["ir.config_parameter"].sudo().get_param("site_labour_management.expense_account_id", 0)
        )
        if not expense_account:
            raise UserError("Please configure Labour Expense Account in settings.")

        for rec in self:
            if rec.move_id:
                continue
            lines = []
            analytic = rec.sheet_ids[:1].analytic_account_id
            for line in rec.line_ids:
                lines.append(
                    (
                        0,
                        0,
                        {
                            "name": f"Labour charges - {line.source}",
                            "account_id": expense_account,
                            "quantity": 1,
                            "price_unit": line.amount,
                            "analytic_distribution": {analytic.id: 100} if analytic else False,
                        },
                    )
                )
            move = self.env["account.move"].create(
                {
                    "move_type": "in_invoice",
                    "invoice_date": fields.Date.today(),
                    "partner_id": rec.partner_id.id,
                    "invoice_line_ids": lines,
                    "invoice_origin": rec.name,
                }
            )
            rec.write({"move_id": move.id, "state": "billed"})
            rec.sheet_ids.write({"billing_status": "billed"})
            rec.partner_id._slm_send_whatsapp(
                f"Vendor bill {move.name or move.id} created for amount {rec.amount_total:.2f}."
            )


class SiteLabourWeeklyBillLine(models.Model):
    _name = "site.labour.weekly.bill.line"
    _description = "Site Labour Weekly Bill Line"

    weekly_bill_id = fields.Many2one("site.labour.weekly.bill", required=True, ondelete="cascade")
    source = fields.Char(required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="weekly_bill_id.currency_id", store=True)
