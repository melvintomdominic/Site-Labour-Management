from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class SiteLabourSheet(models.Model):
    _name = "site.labour.sheet"
    _description = "Site Labour Sheet"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    date = fields.Date(required=True, default=fields.Date.context_today)
    attendance_type = fields.Selection(
        [("individual", "Individual"), ("team", "Team Based")], default="individual", required=True
    )
    analytic_account_id = fields.Many2one("account.analytic.account", string="Project", required=True)
    team_leader_id = fields.Many2one("res.partner", domain=[("parent_id", "=", False)])
    team_labour_ids = fields.Many2many(
        "res.partner",
        string="Team Labour",
        domain="[('parent_id','=',team_leader_id)]",
    )
    labour_line_ids = fields.One2many("site.labour.line", "sheet_id", string="Labour Lines")
    supervisor_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved")],
        default="draft",
        tracking=True,
    )
    latitude = fields.Float(digits=(8, 6))
    longitude = fields.Float(digits=(9, 6))
    photo_ids = fields.One2many("site.labour.photo", "sheet_id")
    total_amount = fields.Monetary(compute="_compute_total", store=True)
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id.id, required=True)
    billing_status = fields.Selection(
        [("pending", "Pending"), ("billed", "Billed")], default="pending", tracking=True
    )
    billing_frequency = fields.Selection(
        [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        default=lambda self: self.env["ir.config_parameter"].sudo().get_param(
            "site_labour_management.billing_frequency", "weekly"
        ),
        required=True,
    )

    _sql_constraints = [
        (
            "analytic_date_supervisor_unique",
            "unique(date, analytic_account_id, supervisor_id)",
            "A sheet already exists for this project/date/supervisor.",
        )
    ]

    @api.depends("labour_line_ids.total")
    def _compute_total(self):
        for rec in self:
            rec.total_amount = sum(rec.labour_line_ids.mapped("total"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("site.labour.sheet") or "New"
        return super().create(vals_list)

    @api.onchange("team_leader_id")
    def _onchange_team_leader(self):
        if not self.team_leader_id:
            self.team_labour_ids = [(5, 0, 0)]
            return
        members = self.env["res.partner"].search(
            [("parent_id", "=", self.team_leader_id.id)]
        )
        self.team_labour_ids = [(6, 0, members.ids)]
        if self.attendance_type == "team":
            self.labour_line_ids = [
                (0, 0, {"labour_id": member.id, "hours": 1.0}) for member in members
            ]

    @api.onchange("attendance_type")
    def _onchange_attendance_type(self):
        if self.attendance_type == "individual":
            self.team_leader_id = False
            self.team_labour_ids = [(5, 0, 0)]

    def action_submit(self):
        for rec in self:
            if rec.attendance_type == "team" and not rec.team_leader_id:
                raise UserError("Team Leader is required before submitting.")
            if rec.attendance_type == "team" and not rec.team_labour_ids:
                raise UserError("Select team labour members before submitting.")
            if not rec.latitude or not rec.longitude:
                raise UserError("GPS latitude and longitude are mandatory before submitting.")
            if not rec.photo_ids:
                raise UserError("At least one photo is required before submitting.")
            if not rec.labour_line_ids:
                raise UserError("Add at least one labour line before submitting.")
            rec.state = "submitted"

    def action_reset_draft(self):
        self.write({"state": "draft"})

    def action_assign_analytic_account(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Assign Analytic Account",
            "res_model": "site.labour.analytic.bulk.assign.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"active_model": self._name, "active_ids": self.ids},
        }

    def action_approve(self):
        weekly_model = self.env["site.labour.weekly.bill"]
        for rec in self:
            if rec.state != "submitted":
                raise UserError("Only submitted sheets can be approved.")
            if not rec.labour_line_ids:
                raise UserError("No labour lines found.")
            rec._push_to_weekly_bills(weekly_model)
            rec._create_daily_wage_slips()
            rec.state = "approved"
            rec.supervisor_id.partner_id._slm_send_whatsapp(
                f"Labour sheet {rec.name} has been approved for {rec.total_amount:.2f}."
            )

    def _push_to_weekly_bills(self, weekly_model):
        self.ensure_one()
        if self.attendance_type == "team":
            if not self.team_leader_id:
                raise UserError("Team Leader is required for team billing.")
            bill = weekly_model.get_or_create_for(self.team_leader_id, self.date, self.billing_frequency or "weekly")
            amount = sum(self.labour_line_ids.mapped("total"))
            existing = bill.line_ids.filtered(lambda l: l.source == self.name)
            if existing:
                existing.amount = amount
            else:
                bill.line_ids = [(0, 0, {"source": self.name, "amount": amount})]
            if self not in bill.sheet_ids:
                bill.sheet_ids = [(4, self.id)]
            if bill.state == "draft":
                bill.action_create_vendor_bill()
            return

        for line in self.labour_line_ids:
            bill = weekly_model.get_or_create_for(line.labour_id, self.date, self.billing_frequency or "weekly")
            source = f"{self.name}-{line.labour_id.id}"
            existing = bill.line_ids.filtered(lambda l: l.source == source)
            if existing:
                existing.amount = line.total
            else:
                bill.line_ids = [(0, 0, {"source": source, "amount": line.total})]
            if self not in bill.sheet_ids:
                bill.sheet_ids = [(4, self.id)]
            if bill.state == "draft":
                bill.action_create_vendor_bill()

    def _create_daily_wage_slips(self):
        self.ensure_one()
        daily_model = self.env["site.labour.daily.wage.slip"]
        for line in self.labour_line_ids:
            vals = {
                "work_date": self.date,
                "work_type": line.category_id.id,
                "labour_group": self.team_leader_id.name if self.attendance_type == "team" else "Individual",
                "labour_id": line.labour_id.id,
                "work": self.analytic_account_id.display_name or "",
                "days_count": 1.0,
                "no_of_labours_worked": 1,
                "basic_wage_day": line.wage,
                "overtime_duration": line.ot_hours,
                "overtime_wage": line.ot_hours * line.category_id.ot_rate,
                "sheet_id": self.id,
                "remarks": f"Auto-generated from {self.name}",
            }
            existing = daily_model.search(
                [("sheet_id", "=", self.id), ("labour_id", "=", line.labour_id.id), ("work_type", "=", line.category_id.id)],
                limit=1,
            )
            if existing:
                existing.write(vals)
            else:
                daily_model.create(vals)

    @api.model
    def cron_missing_entry_reminder(self):
        today = fields.Date.today()
        supervisors = self.env["res.users"].search([])
        for supervisor in supervisors:
            existing = self.search_count(
                [("date", "=", today), ("supervisor_id", "=", supervisor.id), ("state", "in", ["draft", "submitted", "approved"])]
            )
            if not existing:
                supervisor.partner_id._slm_send_whatsapp(
                    f"Reminder: submit labour sheet for {today.strftime('%d-%b-%Y')} before 7 PM."
                )

    @api.model
    def cron_payment_reminder(self):
        moves = self.env["account.move"].search(
            [
                ("move_type", "=", "in_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "!=", "paid"),
                ("invoice_date_due", "<", fields.Date.today()),
            ]
        )
        for move in moves:
            move.partner_id._slm_send_whatsapp(
                f"Payment reminder: invoice {move.name} of {move.amount_residual:.2f} is overdue."
            )


class SiteLabourLine(models.Model):
    _name = "site.labour.line"
    _description = "Site Labour Line"

    sheet_id = fields.Many2one("site.labour.sheet", required=True, ondelete="cascade")
    labour_id = fields.Many2one("res.partner", required=True, domain=[("parent_id", "!=", False)])
    category_id = fields.Many2one("site.labour.category", required=True)
    wage = fields.Monetary(required=True, currency_field="currency_id")
    hours = fields.Float(default=1.0)
    ot_hours = fields.Float(compute="_compute_ot_hours", store=True)
    total = fields.Monetary(compute="_compute_total", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="sheet_id.currency_id", store=True)

    @api.onchange("category_id")
    def _onchange_category_id(self):
        self.wage = self.category_id.default_wage

    @api.depends("hours")
    def _compute_ot_hours(self):
        default_ot = float(self.env["ir.config_parameter"].sudo().get_param("site_labour_management.default_ot_hours", 9.0))
        for rec in self:
            rec.ot_hours = max(rec.hours - default_ot, 0)

    @api.depends("wage", "hours", "ot_hours", "category_id.ot_rate")
    def _compute_total(self):
        for rec in self:
            rec.total = (rec.wage * rec.hours) + (rec.ot_hours * rec.category_id.ot_rate)

    @api.constrains("sheet_id", "labour_id")
    def _check_duplicate_worker(self):
        for rec in self:
            duplicate = self.search_count(
                [("id", "!=", rec.id), ("sheet_id", "=", rec.sheet_id.id), ("labour_id", "=", rec.labour_id.id)]
            )
            if duplicate:
                raise ValidationError("The same labour cannot be entered twice in one sheet.")
