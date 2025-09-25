from odoo import fields, models, api, _


class StockLocation(models.Model):
    " inherit stock location model to add new field "
    
    _inherit = "stock.location"
    
    location_adjustment = fields.Boolean('Location Adjustment', default = False)