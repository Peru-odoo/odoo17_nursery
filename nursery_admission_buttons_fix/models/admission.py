from odoo import models, fields

class NurseryAdmission(models.Model):
    _name = 'nursery.admission'
    _description = 'Nursery Admission'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    child_name = fields.Char()
    birth_date = fields.Date()
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    application_date = fields.Date(default=fields.Date.today,readonly=True)

    status = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ], default='draft', tracking=True)
    parent_id = fields.Many2one('res.partner', string="Parent")

    def action_accept(self):
        for rec in self:
            rec.status = 'accepted'

    def action_reject(self):
        for rec in self:
            rec.status = 'rejected'
