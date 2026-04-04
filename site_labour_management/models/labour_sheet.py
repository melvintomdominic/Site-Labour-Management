import base64
from urllib import parse, request

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _slm_send_whatsapp(self, message):
        param = self.env["ir.config_parameter"].sudo()
        sid = param.get_param("site_labour_management.twilio_sid")
        token = param.get_param("site_labour_management.twilio_token")
        from_number = param.get_param("site_labour_management.twilio_from_number")
        if not (sid and token and from_number):
            return False

        for partner in self.filtered("mobile"):
            url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
            payload = parse.urlencode(
                {"From": f"whatsapp:{from_number}", "To": f"whatsapp:{partner.mobile}", "Body": message}
            ).encode()
            req = request.Request(url, data=payload, method="POST")
            auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            try:
                request.urlopen(req, timeout=10)
            except Exception:
                continue
        return True


class SiteLabourSheet(models.Model):
    _name = "site.labour.sheet"
    _description = "Site Labour Sheet"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(default="New", readonly=True, copy=False)
    date = fields.Date(required=True, default=fields.Date.context_today)
    attendance_type = fields.Selection(
        [("team", "Team Based"), ("individual", "Individual")], default="team", required=True
    )
    project_id = fields.Many2one("project.project")
    analytic_account_id = fields.Many2one("account.analytic.account", string="Project", required=True)
    team_leader_id = fields.Many2one(
        "res.partner", domain=[("is_company", "=", True)], required=True
    )
    labour_ids = fields.Many2many("res.partner", string="Sub Labours")
    labour_id = fields.Many2one("res.partner", string="Labour")
    supervisor_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user)
    state = fields.Selection(
        [("draft", "Draft"), ("submitted", "Submitted"), ("approved", "Approved")],
        default="draft",
        tracking=True,
    )
    latitude = fields.Float(digits=(8, 6))
    longitude = fields.Float(digits=(9, 6))
    photo_ids = fields.One2many("site.labour.photo", "sheet_id")
    team_line_ids = fields.One2many("site.labour.team.line", "sheet_id")
    individual_line_ids = fields.One2many("site.labour.individual.line", "sheet_id")
    total_amount = fields.Monetary(compute="_compute_total", store=True)
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id.id, required=True
    )
    billing_status = fields.Selection(
        [("pending", "Pending"), ("billed", "Billed")],
        default="pending",
        tracking=True,
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
            "project_date_supervisor_unique",
            "unique(date, project_id, supervisor_id)",
            "A sheet already exists for this project/date/supervisor.",
        )
    ]

    @api.depends("team_line_ids.total", "individual_line_ids.total")
    def _compute_total(self):
        for rec in self:
            rec.total_amount = sum(rec.team_line_ids.mapped("total")) + sum(
                rec.individual_line_ids.mapped("total")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("site.labour.sheet") or "New"
        return super().create(vals_list)

    @api.onchange("project_id")
    def _onchange_project_id(self):
        if not self.project_id:
            return
        # Odoo 17/18: project analytic link may not expose analytic_account_id.
        if hasattr(self.project_id, "account_id") and self.project_id.account_id:
            self.analytic_account_id = self.project_id.account_id
        elif hasattr(self.project_id, "analytic_account_id") and self.project_id.analytic_account_id:
            self.analytic_account_id = self.project_id.analytic_account_id
        else:
            # Keep user-safe fallback to avoid onchange crashes.
            self.analytic_account_id = False

    @api.onchange("team_leader_id")
    def _onchange_team_leader_id(self):
        if not self.team_leader_id:
            self.labour_ids = [(5, 0, 0)]
            return
        self.labour_ids = [(6, 0, self.team_leader_id.child_ids.ids)]

    @api.onchange("attendance_type")
    def _onchange_attendance_type(self):
        if self.attendance_type == "individual":
            self.team_leader_id = False
            self.labour_ids = [(5, 0, 0)]
        else:
            self.labour_id = False

    def action_submit(self):
        for rec in self:
            if rec.attendance_type == "team" and not rec.team_leader_id:
                raise UserError("Team Leader is required before submitting.")
            if rec.attendance_type == "team" and not rec.labour_ids:
                raise UserError("Select at least one labour under the Team Leader.")
            if rec.attendance_type == "individual" and not rec.labour_id:
                raise UserError("Labour is required for Individual attendance.")
            if not rec.latitude or not rec.longitude:
                raise UserError("GPS latitude and longitude are mandatory before submitting.")
            if not rec.photo_ids:
                raise UserError("At least one photo is required before submitting.")
            if not (rec.team_line_ids or rec.individual_line_ids):
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
            rec._check_for_approval()
            rec._push_to_weekly_bills(weekly_model)
            rec._create_daily_wage_slips()
            rec.state = "approved"
            rec.supervisor_id.partner_id._slm_send_whatsapp(
                f"Labour sheet {rec.name} has been approved for {rec.total_amount:.2f}."
            )

    def _check_for_approval(self):
        self.ensure_one()
        if not (self.team_line_ids or self.individual_line_ids):
            raise UserError("No labour lines found.")

    def _push_to_weekly_bills(self, weekly_model):
        self.ensure_one()
        partner = self.team_leader_id if self.attendance_type == "team" else self.labour_id
        if not partner:
            raise UserError("Payment partner is required for billing.")
        amount = self.total_amount
        bill = weekly_model.get_or_create_for(
            partner, self.date, self.billing_frequency or "weekly"
        )
        if self not in bill.sheet_ids:
            bill.sheet_ids = [(4, self.id)]
        existing = bill.line_ids.filtered(lambda l: l.source == self.name)
        if existing:
            existing.amount = amount
        else:
            bill.line_ids = [(0, 0, {"source": self.name, "amount": amount})]
        if bill.state == "draft":
            bill.action_create_vendor_bill()

    def _create_daily_wage_slips(self):
        self.ensure_one()
        daily_model = self.env["site.labour.daily.wage.slip"]
        for line in self.team_line_ids:
            vals = {
                "work_date": self.date,
                "project_id": self.project_id.id,
                "work_type": line.category_id.id,
                "labour_group": line.team_leader_id.name,
                "labour_id": line.team_leader_id.id,
                "work": self.analytic_account_id.display_name or "",
                "days_count": 1.0,
                "no_of_labours_worked": line.labour_count,
                "basic_wage_day": line.wage,
                "daily_wage_rate": line.wage,
                "overtime_duration": line.ot_hours,
                "overtime_wage": line.ot_hours * line.category_id.ot_rate,
                "sheet_id": self.id,
                "remarks": f"Auto-generated from {self.name}",
            }
            existing = daily_model.search(
                [
                    ("sheet_id", "=", self.id),
                    ("labour_id", "=", line.team_leader_id.id),
                    ("work_type", "=", line.category_id.id),
                ],
                limit=1,
            )
            if existing:
                existing.write(vals)
            else:
                daily_model.create(vals)

        for line in self.individual_line_ids:
            vals = {
                "work_date": self.date,
                "project_id": self.project_id.id,
                "work_type": line.category_id.id,
                "labour_group": "Individual",
                "employee_id": line.employee_id.id,
                "labour_id": line.labour_id.id,
                "work": self.analytic_account_id.display_name or "",
                "days_count": 1.0,
                "no_of_labours_worked": 1,
                "basic_wage_day": line.wage,
                "daily_wage_rate": line.daily_wage_rate or line.wage,
                "overtime_duration": line.ot_hours,
                "overtime_wage": line.ot_hours * line.category_id.ot_rate,
                "sheet_id": self.id,
                "remarks": f"Auto-generated from {self.name}",
            }
            existing = daily_model.search(
                [
                    ("sheet_id", "=", self.id),
                    ("labour_id", "=", line.labour_id.id),
                    ("work_type", "=", line.category_id.id),
                ],
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
                [
                    ("date", "=", today),
                    ("supervisor_id", "=", supervisor.id),
                    ("state", "in", ["draft", "submitted", "approved"]),
                ]
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


class SiteLabourTeamLine(models.Model):
    _name = "site.labour.team.line"
    _description = "Site Team Labour Line"

    sheet_id = fields.Many2one("site.labour.sheet", required=True, ondelete="cascade")
    team_leader_id = fields.Many2one("res.partner", required=True)
    category_id = fields.Many2one("site.labour.category", required=True)
    labour_count = fields.Integer(required=True, default=1)
    wage = fields.Monetary(required=True, currency_field="currency_id")
    worked_hours = fields.Float(string="Hours", default=9.0)
    ot_hours = fields.Float(compute="_compute_ot_hours", store=True)
    total = fields.Monetary(compute="_compute_total", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="sheet_id.currency_id", store=True)

    @api.onchange("category_id")
    def _onchange_category_id(self):
        self.wage = self.category_id.default_wage

    @api.depends("worked_hours")
    def _compute_ot_hours(self):
        default_ot = float(
            self.env["ir.config_parameter"].sudo().get_param("site_labour_management.default_ot_hours", 9.0)
        )
        for rec in self:
            rec.ot_hours = max(rec.worked_hours - default_ot, 0)

    @api.depends("labour_count", "wage", "ot_hours", "category_id.ot_rate")
    def _compute_total(self):
        for rec in self:
            rec.total = (rec.labour_count * rec.wage) + (rec.ot_hours * rec.category_id.ot_rate)


class SiteLabourIndividualLine(models.Model):
    _name = "site.labour.individual.line"
    _description = "Site Individual Labour Line"

    sheet_id = fields.Many2one("site.labour.sheet", required=True, ondelete="cascade")
    employee_id = fields.Many2one("hr.employee")
    labour_id = fields.Many2one("res.partner", required=True)
    category_id = fields.Many2one("site.labour.category", required=True)
    daily_wage_rate = fields.Float()
    wage = fields.Monetary(required=True, currency_field="currency_id")
    worked_hours = fields.Float(string="Hours", default=9.0)
    ot_hours = fields.Float(compute="_compute_ot_hours", store=True)
    total = fields.Monetary(compute="_compute_total", store=True, currency_field="currency_id")
    currency_id = fields.Many2one(related="sheet_id.currency_id", store=True)

    @api.onchange("category_id")
    def _onchange_category_id(self):
        self.wage = self.category_id.default_wage

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        if not self.employee_id:
            return
        self.labour_id = self.employee_id.address_home_id or self.labour_id
        rate = self.env["site.labour.employee.wage"].get_latest_rate(
            self.employee_id, self.sheet_id.date or fields.Date.context_today(self)
        )
        self.daily_wage_rate = rate
        if rate:
            self.wage = rate

    @api.depends("worked_hours")
    def _compute_ot_hours(self):
        default_ot = float(
            self.env["ir.config_parameter"].sudo().get_param("site_labour_management.default_ot_hours", 9.0)
        )
        for rec in self:
            rec.ot_hours = max(rec.worked_hours - default_ot, 0)

    @api.depends("wage", "ot_hours", "category_id.ot_rate")
    def _compute_total(self):
        for rec in self:
            rec.total = rec.wage + (rec.ot_hours * rec.category_id.ot_rate)

    @api.constrains("sheet_id", "labour_id")
    def _check_duplicate_worker(self):
        for rec in self:
            duplicate = self.search_count(
                [
                    ("id", "!=", rec.id),
                    ("sheet_id", "=", rec.sheet_id.id),
                    ("labour_id", "=", rec.labour_id.id),
                ]
            )
            if duplicate:
                raise ValidationError("The same labour cannot be entered twice in one sheet.")
