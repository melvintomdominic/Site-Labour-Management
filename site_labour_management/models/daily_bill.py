from odoo import api, fields, models
from odoo.exceptions import UserError


class SiteLabourDailyBill(models.Model):
    _name = "site.labour.daily.bill"
    _description = "Site Labour Daily Bill"
    _order = "date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    date = fields.Date(required=True, default=fields.Date.context_today)
    partner_id = fields.Many2one("res.partner", required=True, domain=[("is_team_leader", "=", True)])
    labour_sheet_ids = fields.Many2many("site.labour.sheet")
    line_ids = fields.One2many("site.labour.daily.bill.line", "bill_id")
    total_amount = fields.Monetary(compute="_compute_total_amount", store=True)
    analytic_account_id = fields.Many2one("account.analytic.account", string="Project")
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

    @api.onchange("labour_sheet_ids")
    def _onchange_labour_sheet_ids(self):
        self._populate_lines_from_sheets()

    def _populate_lines_from_sheets(self):
        for rec in self:
            if not rec.partner_id and rec.labour_sheet_ids:
                rec.partner_id = rec.labour_sheet_ids[:1].team_leader_id
            lines = [(5, 0, 0)]
            for sheet in rec.labour_sheet_ids:
                if rec.partner_id and sheet.attendance_type == "team" and sheet.team_leader_id != rec.partner_id:
                    continue
                for line in sheet.labour_line_ids:
                    lines.append(
                        (
                            0,
                            0,
                            {
                                "labour_id": line.labour_id.id,
                                "work_type": line.category_id.name,
                                "quantity": line.hours,
                                "rate": line.wage,
                            },
                        )
                    )
            rec.line_ids = lines

    def action_confirm(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError("Cannot confirm daily bill without lines.")
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
            if rec.move_id:
                rec.state = "posted"
                continue
            if rec.labour_sheet_ids.filtered(lambda s: s.billing_status == "billed"):
                raise UserError("One or more linked labour sheets are already billed.")

            invoice_lines = [
                (
                    0,
                    0,
                    {
                        "name": f"Daily Bill {line.work_type or rec.name}",
                        "account_id": expense_account_id,
                        "quantity": line.quantity,
                        "price_unit": line.rate,
                        "analytic_distribution": {rec.analytic_account_id.id: 100} if rec.analytic_account_id else False,
                    },
                )
                for line in rec.line_ids
            ]
            move = self.env["account.move"].create(
                {
                    "move_type": "in_invoice",
                    "invoice_date": rec.date,
                    "partner_id": rec.partner_id.id,
                    "invoice_origin": rec.name,
                    "invoice_line_ids": invoice_lines,
                }
            )
            rec.write({"move_id": move.id, "state": "posted"})
            rec.labour_sheet_ids.write({"billing_status": "billed"})


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
