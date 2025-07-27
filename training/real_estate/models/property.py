from odoo import models, fields

class Property(models.Model):
    _name = 'real.estate.property'
    _description = 'Real Estate Property'

    name = fields.Char(required=True)
    description = fields.Text()
    price = fields.Float()
    area = fields.Float(string="Area (sqft)")
    bedrooms = fields.Integer()
    bathrooms = fields.Integer()
    address = fields.Char()
    status = fields.Selection([('available', 'Available'), ('sold', 'Sold')], default='available')
    agent_id = fields.Many2one('real.estate.agent', string="Agent")
    feature_ids = fields.One2many('real.estate.feature', 'property_id', string="Features")
    booking_ids = fields.One2many('real.estate.booking', 'property_id', string="Bookings")
