from odoo import models, fields

class Agent(models.Model):
    _name = 'real.estate.agent'
    _description = 'Real Estate Agent'

    name = fields.Char(required=True)
    email = fields.Char()
    phone = fields.Char()
    image = fields.Binary()
    property_ids = fields.One2many('real.estate.property', 'agent_id', string="Properties")
