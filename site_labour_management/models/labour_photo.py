from odoo import fields, models


class SiteLabourPhoto(models.Model):
    _name = "site.labour.photo"
    _description = "Site Labour Photo"

    name = fields.Char(default="Labour Photo")
    image = fields.Image(required=True)
    image_type = fields.Selection(
        [("work", "Work"), ("labour", "Labour Proof")], required=True, default="work"
    )
    sheet_id = fields.Many2one("site.labour.sheet", required=True, ondelete="cascade")
