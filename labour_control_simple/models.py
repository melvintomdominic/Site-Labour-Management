from odoo import fields, models
from odoo.exceptions import UserError


class LabourAttendance(models.Model):
    _name = 'labour.attendance'
    _description = 'Labour Attendance'

    date = fields.Date(default=fields.Date.today)
    project_id = fields.Many2one('project.project', required=True)
    supervisor_id = fields.Many2one('res.partner', required=True)
    photo = fields.Binary()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved')
    ], default='draft')
    line_ids = fields.One2many('labour.attendance.line', 'attendance_id')

    def action_confirm(self):
        for rec in self:
            if not rec.photo:
                raise UserError('Photo required')

            expense_account = self.env['account.account'].search(
                [('internal_group', '=', 'expense')], limit=1
            )
            if not expense_account:
                raise UserError('No expense account found')

            lines = []
            for line in rec.line_ids:
                if not line.present:
                    continue
                total = line.days * line.rate
                lines.append((0, 0, {
                    'name': line.labour_id.name,
                    'quantity': 1,
                    'price_unit': total,
                    'account_id': expense_account.id,
                }))

            if not lines:
                raise UserError('No present labour lines to bill')

            bill = self.env['account.move'].create({
                'move_type': 'in_invoice',
                'partner_id': rec.supervisor_id.id,
                'invoice_date': rec.date,
                'invoice_line_ids': lines,
            })
            bill.action_post()
            rec.state = 'approved'


class LabourAttendanceLine(models.Model):
    _name = 'labour.attendance.line'
    _description = 'Labour Attendance Line'

    attendance_id = fields.Many2one('labour.attendance', ondelete='cascade')
    labour_id = fields.Many2one('res.partner', required=True)
    present = fields.Boolean(default=True)
    days = fields.Float(default=1)
    rate = fields.Float()
