from odoo import fields, models


class SiteLabourAnalyticBulkAssignWizard(models.TransientModel):
    _name = "site.labour.analytic.bulk.assign.wizard"
    _description = "Assign Analytic Account in Bulk"

    analytic_account_id = fields.Many2one("account.analytic.account", required=True)
    wage_rate = fields.Float(string="Wage Rate")

    def action_apply(self):
        active_model = self.env.context.get("active_model")
        active_ids = self.env.context.get("active_ids", [])
        if active_model in ("site.labour.sheet", "site.labour.weekly.bill") and active_ids:
            records = self.env[active_model].browse(active_ids)
            records.write({"analytic_account_id": self.analytic_account_id.id})
            if active_model == "site.labour.sheet" and self.wage_rate:
                records.mapped("labour_line_ids").write({"wage": self.wage_rate})
        return {"type": "ir.actions.act_window_close"}
