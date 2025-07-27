from odoo import models, fields

class Booking(models.Model):
    _name = 'real.estate.booking'
    _description = 'Property Booking'

    property_id = fields.Many2one('real.estate.property', string="Property")
    buyer_id = fields.Many2one('res.partner', string="Buyer")
    booking_date = fields.Date()
    status = fields.Selection([('pending', 'Pending'), ('confirmed', 'Confirmed')], default='pending')
