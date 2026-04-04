from odoo import api, fields, models
from odoo.exceptions import UserError


class SiteLabourDailyWageSlip(models.Model):
    _name = "site.labour.daily.wage.slip"
    _description = "Labour Daily Wage Slip"
    _order = "work_date asc, id asc"

    name = fields.Char(default="New", readonly=True, copy=False)
    work_date = fields.Date(required=True, default=fields.Date.context_today)
    day_name = fields.Char(compute="_compute_day_name", store=True)
    project_id = fields.Many2one("project.project")
    employee_id = fields.Many2one("hr.employee")
    work_type = fields.Many2one("site.labour.category", required=True)
    labour_group = fields.Char()
    labour_id = fields.Many2one("res.partner", required=True)
    work = fields.Char()
    days_count = fields.Float(default=1.0)
    no_of_labours_worked = fields.Integer(default=1)
    basic_wage_day = fields.Monetary(currency_field="currency_id")
    daily_wage_rate = fields.Float()
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
            wage_rate = rec.daily_wage_rate or rec.basic_wage_day
            base = rec.days_count * rec.no_of_labours_worked * wage_rate
            rec.total_wage = base + rec.overtime_wage + rec.extra_wage + rec.ta_wage + rec.food_allowance - rec.deduction

    @api.onchange("employee_id", "work_date")
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        rate = self.env["site.labour.employee.wage"].get_latest_rate(
            self.employee_id, self.work_date or fields.Date.context_today(self)
        )
        self.daily_wage_rate = rate
        if rate:
            self.basic_wage_day = rate

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
    employee_id = fields.Many2one("hr.employee")
    work_type = fields.Many2one("site.labour.category")
    paid_amount = fields.Monetary(required=True, currency_field="currency_id")
    debit_account_id = fields.Many2one("account.account")
    expense_account_id = fields.Many2one("account.account")
    analytic_account_id = fields.Many2one("account.analytic.account")
    journal_id = fields.Many2one("account.journal")
    payment_mode = fields.Selection(
        [("cash", "Cash"), ("bank", "Bank"), ("upi", "UPI"), ("other", "Other")], default="bank"
    )
    tr_ref_no = fields.Char()
    tr_ref_date = fields.Date()
    remarks = fields.Char()
    slip_id = fields.Many2one("site.labour.daily.wage.slip")
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
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

    @api.onchange("slip_id")
    def _onchange_slip_id(self):
        if not self.slip_id:
            return
        self.labour_id = self.slip_id.labour_id
        self.employee_id = self.slip_id.employee_id
        self.paid_amount = self.slip_id.total_wage
        self.analytic_account_id = self.slip_id.sheet_id.analytic_account_id

    @api.onchange("employee_id", "paid_date")
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        rate = self.env["site.labour.employee.wage"].get_latest_rate(
            self.employee_id, self.paid_date or fields.Date.context_today(self)
        )
        if rate and not self.paid_amount:
            self.paid_amount = rate

    def action_confirm_payment(self):
        param = self.env["ir.config_parameter"].sudo()
        default_expense_account = int(param.get_param("site_labour_management.expense_account_id", 0))
        for rec in self:
            expense_account = rec.expense_account_id or self.env["account.account"].browse(default_expense_account)
            if not expense_account:
                raise UserError("Configure Labour Expense Account or set Expense Account on payment.")
            if not rec.debit_account_id:
                raise UserError("Payment account is required to post wage payment.")
            if not rec.analytic_account_id:
                raise UserError("Analytic Account is required to post wage payment.")
            if rec.employee_id:
                rate = self.env["site.labour.employee.wage"].get_latest_rate(
                    rec.employee_id, rec.paid_date or fields.Date.context_today(self)
                )
                if not rate:
                    raise UserError("Wage rate missing for selected employee.")
            if not rec.journal_id:
                raise UserError("Journal is required to post wage payment.")
            if rec.move_id:
                continue

            line_vals = [
                (
                    0,
                    0,
                    {
                        "name": f"Wage Payment {rec.tr_id}",
                        "account_id": expense_account.id,
                        "debit": rec.paid_amount,
                        "credit": 0.0,
                        "analytic_distribution": {rec.analytic_account_id.id: 100},
                    },
                ),
                (
                    0,
                    0,
                    {
                        "name": f"Wage Payment {rec.tr_id}",
                        "account_id": rec.debit_account_id.id,
                        "debit": 0.0,
                        "credit": rec.paid_amount,
                    },
                ),
            ]
            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": rec.paid_date or fields.Date.context_today(self),
                    "journal_id": rec.journal_id.id,
                    "line_ids": line_vals,
                    "ref": rec.tr_id,
                }
            )
            move.action_post()
            rec.write({"move_id": move.id, "state": "posted"})
