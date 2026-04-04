from datetime import timedelta
import calendar

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
    analytic_account_id = fields.Many2one("account.analytic.account", string="Analytic Account")
    daily_bill_ids = fields.Many2many("site.labour.daily.bill", string="Daily Bills")
    billing_frequency = fields.Selection(
        [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        required=True,
        default="weekly",
    )
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
            "unique(partner_id, week_start, week_end, billing_frequency)",
            "A consolidated bill already exists for this partner and period/frequency.",
        )
    ]

    @api.depends("line_ids.amount")
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.line_ids.mapped("amount"))

    @api.model
    def period_bounds(self, day, frequency):
        day = fields.Date.to_date(day)
        if frequency == "daily":
            return day, day
        if frequency == "monthly":
            start = day.replace(day=1)
            end = day.replace(day=calendar.monthrange(day.year, day.month)[1])
            return start, end
        period_start = day - timedelta(days=day.weekday())
        period_end = period_start + timedelta(days=6)
        return period_start, period_end

    @api.model
    def get_or_create_for(self, partner, day, frequency="weekly"):
        week_start, week_end = self.period_bounds(day, frequency)
        bill = self.search(
            [
                ("partner_id", "=", partner.id),
                ("week_start", "=", week_start),
                ("week_end", "=", week_end),
                ("billing_frequency", "=", frequency),
            ],
            limit=1,
        )
        if not bill:
            bill = self.create(
                {
                    "partner_id": partner.id,
                    "week_start": week_start,
                    "week_end": week_end,
                    "billing_frequency": frequency,
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
            analytic = rec.analytic_account_id or rec.sheet_ids[:1].analytic_account_id
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

    def action_assign_analytic_account(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Assign Analytic Account",
            "res_model": "site.labour.analytic.bulk.assign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_model": self._name, "active_ids": self.ids},
        }

    def action_pull_daily_bills(self):
        for rec in self:
            bills = self.env["site.labour.daily.bill"].search(
                [
                    ("partner_id", "=", rec.partner_id.id),
                    ("date", ">=", rec.week_start),
                    ("date", "<=", rec.week_end),
                    ("state", "in", ["confirmed", "posted"]),
                ]
            )
            rec.daily_bill_ids = [(6, 0, bills.ids)]
            rec.line_ids = [(5, 0, 0)] + [
                (0, 0, {"source": bill.name, "amount": bill.total_amount}) for bill in bills
            ]


class SiteLabourWeeklyBillLine(models.Model):
    _name = "site.labour.weekly.bill.line"
    _description = "Site Labour Weekly Bill Line"

    weekly_bill_id = fields.Many2one("site.labour.weekly.bill", required=True, ondelete="cascade")
    source = fields.Char(required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="weekly_bill_id.currency_id", store=True)
