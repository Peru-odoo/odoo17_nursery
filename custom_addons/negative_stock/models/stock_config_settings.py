from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Our new field
    allow_negative_stock = fields.Boolean(
        string="Allow Negative Stock",
        config_parameter='stock_negative_control.allow_negative_stock',  # Stores value in Odoo system parameters
        help="If unchecked, Odoo will block stock moves that would result in negative quantities."  # Tooltip help text
    )
