from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    child_profile_type = fields.Selection([
        ('child', 'Child'),
        ('parent', 'Parent'),
    ], string="Child Profile Type")
