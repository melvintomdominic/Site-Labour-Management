from odoo import api, fields, models
from odoo.exceptions import UserError


class SiteLabourDailyWageSlip(models.Model):
    _name = "site.labour.daily.wage.slip"
    _description = "Labour Daily Wage Slip"
    _order = "work_date asc, id asc"

    name = fields.Char(default="New", readonly=True, copy=False)
    work_date = fields.Date(required=True, default=fields.Date.context_today)
    day_name = fields.Char(compute="_compute_day_name", store=True)
    work_type = fields.Many2one("site.labour.category", required=True)
    labour_group = fields.Char()
    labour_id = fields.Many2one("res.partner", required=True)
    work = fields.Char()
    days_count = fields.Float(default=1.0)
    no_of_labours_worked = fields.Integer(default=1)
    basic_wage_day = fields.Monetary(currency_field="currency_id")
    overtime_duration = fields.Float()
    overtime_wage = fields.Monetary(currency_field="currency_id")
    extra_wage = fields.Monetary(currency_field="currency_id")
    ta_wage = fields.Monetary(currency_field="currency_id")
    food_allowance = fields.Monetary(currency_field="currency_id")
    deduction = fields.Monetary(currency_field="currency_id")
    total_wage = fields.Monetary(compute="_compute_total_wage", store=True, currency_field="currency_id")
    remarks = fields.Char()
    sheet_id = fields.Many2one("site.labour.sheet", ondelete="set null")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )

    _sql_constraints = [
        (
            "sheet_labour_unique",
            "unique(sheet_id, labour_id, work_type)",
            "Daily wage slip already exists for this labour/work type in this sheet.",
        )
    ]

    @api.depends("work_date")
    def _compute_day_name(self):
        for rec in self:
            rec.day_name = rec.work_date.strftime("%A") if rec.work_date else False

    @api.depends(
        "days_count",
        "no_of_labours_worked",
        "basic_wage_day",
        "overtime_wage",
        "extra_wage",
        "ta_wage",
        "food_allowance",
        "deduction",
    )
    def _compute_total_wage(self):
        for rec in self:
            base = rec.days_count * rec.no_of_labours_worked * rec.basic_wage_day
            rec.total_wage = base + rec.overtime_wage + rec.extra_wage + rec.ta_wage + rec.food_allowance - rec.deduction

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("site.labour.daily.wage.slip") or "New"
        return super().create(vals_list)


class SiteLabourWagePayment(models.Model):
    _name = "site.labour.wage.payment"
    _description = "Labour Wage Payment"
    _order = "paid_date desc, id desc"

    tr_id = fields.Char(default="New", readonly=True, copy=False)
    paid_date = fields.Date(required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one("account.journal", required=True)
    payment_method_line_id = fields.Many2one("account.payment.method.line")
    wage_line_ids = fields.One2many("site.labour.wage.payment.line", "payment_id")
    total_amount = fields.Monetary(compute="_compute_total_amount", store=True, currency_field="currency_id")
    remarks = fields.Char()
    payment_id = fields.Many2one("account.payment", readonly=True, copy=False)
    state = fields.Selection([("draft", "Draft"), ("posted", "Posted")], default="draft", tracking=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("tr_id", "New") == "New":
                vals["tr_id"] = self.env["ir.sequence"].next_by_code("site.labour.wage.payment") or "New"
        return super().create(vals_list)

    @api.depends("wage_line_ids.amount")
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.wage_line_ids.mapped("amount"))

    @api.onchange("journal_id")
    def _onchange_journal_id(self):
        if self.journal_id and self.journal_id.outbound_payment_method_line_ids:
            self.payment_method_line_id = self.journal_id.outbound_payment_method_line_ids[0]

    def action_confirm_payment(self):
        for rec in self:
            if not rec.journal_id:
                raise UserError("Journal is required to post wage payment.")
            if not rec.wage_line_ids:
                raise UserError("Add at least one labour payment line.")
            if rec.total_amount <= 0:
                raise UserError("Total payment amount must be greater than zero.")
            if any(not line.analytic_account_id for line in rec.wage_line_ids):
                raise UserError("All labour payment lines require analytic account.")
            for line in rec.wage_line_ids:
                billed = self.env["site.labour.weekly.bill"].search_count(
                    [
                        ("partner_id", "=", line.labour_id.id),
                        ("state", "=", "billed"),
                        ("move_id", "!=", False),
                    ]
                )
                if not billed:
                    raise UserError(
                        f"Cannot pay {line.labour_id.display_name} without a billed vendor bill."
                    )
            if rec.payment_id:
                continue
            main_partner = rec.wage_line_ids[:1].labour_id
            payment_method = rec.payment_method_line_id or rec.journal_id.outbound_payment_method_line_ids[:1]
            payment = self.env["account.payment"].create(
                {
                    "payment_type": "outbound",
                    "partner_type": "supplier",
                    "partner_id": main_partner.id,
                    "amount": rec.total_amount,
                    "date": rec.paid_date,
                    "journal_id": rec.journal_id.id,
                    "payment_method_line_id": payment_method.id if payment_method else False,
                    "ref": rec.tr_id,
                }
            )
            payment.action_post()
            total = rec.total_amount or 1.0
            distribution = {}
            for line in rec.wage_line_ids:
                key = str(line.analytic_account_id.id)
                distribution[key] = distribution.get(key, 0.0) + ((line.amount / total) * 100)
            for mv_line in payment.move_id.line_ids.filtered(
                lambda l: l.account_id != rec.journal_id.default_account_id
            ):
                mv_line.analytic_distribution = distribution
            rec.write({"payment_id": payment.id, "state": "posted"})


class SiteLabourWagePaymentLine(models.Model):
    _name = "site.labour.wage.payment.line"
    _description = "Labour Wage Payment Line"

    payment_id = fields.Many2one("site.labour.wage.payment", required=True, ondelete="cascade")
    labour_id = fields.Many2one("res.partner", required=True)
    amount = fields.Monetary(required=True, currency_field="currency_id")
    analytic_account_id = fields.Many2one("account.analytic.account", required=True)
    currency_id = fields.Many2one(related="payment_id.currency_id", store=True)
