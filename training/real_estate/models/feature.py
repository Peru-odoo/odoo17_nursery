from odoo import models, fields

class PropertyFeature(models.Model):
    _name = 'real.estate.feature'
    _description = 'Property Feature'

    name = fields.Char(required=True)
    value = fields.Char()
    property_id = fields.Many2one('real.estate.property', string="Property")
