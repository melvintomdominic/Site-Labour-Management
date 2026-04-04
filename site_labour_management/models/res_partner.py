import base64
from urllib import parse, request

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_labour = fields.Boolean(string="Is Labour")
    is_team_leader = fields.Boolean(string="Is Team Leader")

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
