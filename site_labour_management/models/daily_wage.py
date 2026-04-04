from odoo import api, fields, models


class SiteLabourDailyWageSlip(models.Model):
    _name = "site.labour.daily.wage.slip"
    _description = "Labour Daily Wage Slip"
    _order = "work_date asc, id asc"

    name = fields.Char(default="New", readonly=True, copy=False)
    work_date = fields.Date(required=True, default=fields.Date.context_today)
    day_name = fields.Char(compute="_compute_day_name", store=True)
    project_id = fields.Many2one("project.project")
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
    labour_id = fields.Many2one("res.partner", required=True)
    work_type = fields.Many2one("site.labour.category")
    paid_amount = fields.Monetary(required=True, currency_field="currency_id")
    debit_account_id = fields.Many2one("account.account")
    payment_mode = fields.Selection(
        [("cash", "Cash"), ("bank", "Bank"), ("upi", "UPI"), ("other", "Other")], default="bank"
    )
    tr_ref_no = fields.Char()
    tr_ref_date = fields.Date()
    remarks = fields.Char()
    slip_id = fields.Many2one("site.labour.daily.wage.slip")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("tr_id", "New") == "New":
                vals["tr_id"] = self.env["ir.sequence"].next_by_code("site.labour.wage.payment") or "New"
        return super().create(vals_list)
