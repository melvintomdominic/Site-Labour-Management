from odoo import api, fields, models
from odoo.exceptions import UserError


class SiteLabourDailyBill(models.Model):
    _name = "site.labour.daily.bill"
    _description = "Site Labour Daily Bill"
    _order = "date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    date = fields.Date(required=True, default=fields.Date.context_today)
    project_id = fields.Many2one("project.project", required=True)
    partner_id = fields.Many2one("res.partner", required=True)
    labour_sheet_ids = fields.Many2many("site.labour.sheet")
    line_ids = fields.One2many("site.labour.daily.bill.line", "bill_id")
    total_amount = fields.Monetary(compute="_compute_total_amount", store=True)
    analytic_account_id = fields.Many2one("account.analytic.account")
    move_id = fields.Many2one("account.move", readonly=True, copy=False)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed"), ("posted", "Posted")],
        default="draft",
        tracking=True,
    )
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )

    @api.depends("line_ids.amount")
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = sum(rec.line_ids.mapped("amount"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("site.labour.daily.bill") or "New"
        return super().create(vals_list)

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if self.project_id and hasattr(self.project_id, "account_id"):
            self.analytic_account_id = self.project_id.account_id

    @api.onchange("labour_sheet_ids")
    def _onchange_labour_sheet_ids(self):
        self._populate_lines_from_sheets()

    def _populate_lines_from_sheets(self):
        for rec in self:
            lines = [(5, 0, 0)]
            for sheet in rec.labour_sheet_ids:
                for line in sheet.individual_line_ids:
                    if rec.partner_id and line.labour_id != rec.partner_id:
                        continue
                    qty = 1
                    rate = line.daily_wage_rate or line.wage
                    lines.append(
                        (
                            0,
                            0,
                            {
                                "labour_id": line.labour_id.id,
                                "work_type": line.category_id.name,
                                "quantity": qty,
                                "rate": rate,
                            },
                        )
                    )
            rec.line_ids = lines

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError("Cannot confirm daily bill without lines.")
            if not rec.analytic_account_id:
                raise UserError("Analytic account is required before confirming daily bill.")
            if any(line.rate <= 0 for line in rec.line_ids):
                raise UserError("All daily bill lines must have wage/rate before confirming.")
            rec.state = "confirmed"

    def action_post(self):
        expense_account_id = int(
            self.env["ir.config_parameter"].sudo().get_param("site_labour_management.expense_account_id", 0)
        )
        if not expense_account_id:
            raise UserError("Please configure Labour Expense Account.")

        for rec in self:
            if not rec.analytic_account_id:
                raise UserError("Analytic account is required before posting.")
            payable_account = rec.partner_id.property_account_payable_id
            if not payable_account:
                raise UserError("Partner payable account is missing.")
            journal = self.env["account.journal"].search([("type", "=", "general")], limit=1)
            if not journal:
                raise UserError("No general journal found for posting.")
            if rec.move_id:
                rec.state = "posted"
                continue

            move = self.env["account.move"].create(
                {
                    "move_type": "entry",
                    "date": rec.date,
                    "journal_id": journal.id,
                    "ref": rec.name,
                    "line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": f"Daily Bill {rec.name}",
                                "account_id": expense_account_id,
                                "debit": rec.total_amount,
                                "credit": 0.0,
                                "analytic_distribution": {rec.analytic_account_id.id: 100},
                            },
                        ),
                        (
                            0,
                            0,
                            {
                                "name": f"Daily Bill {rec.name}",
                                "account_id": payable_account.id,
                                "debit": 0.0,
                                "credit": rec.total_amount,
                            },
                        ),
                    ],
                }
            )
            move.action_post()
            rec.write({"move_id": move.id, "state": "posted"})


class SiteLabourDailyBillLine(models.Model):
    _name = "site.labour.daily.bill.line"
    _description = "Site Labour Daily Bill Line"

    bill_id = fields.Many2one("site.labour.daily.bill", required=True, ondelete="cascade")
    labour_id = fields.Many2one("res.partner", required=True)
    work_type = fields.Char()
    quantity = fields.Float(default=1.0)
    rate = fields.Monetary(currency_field="currency_id")
    amount = fields.Monetary(compute="_compute_amount", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="bill_id.currency_id", store=True)

    @api.depends("quantity", "rate")
    def _compute_amount(self):
        for rec in self:
            rec.amount = rec.quantity * rec.rate
