from odoo import models, fields

class NurseryAdmissionStage(models.Model):
    _name = 'nursery.admission.stage'
    _description = 'Nursery Admission Stage'
    _order = 'sequence'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=1)
    email_template_id = fields.Many2one('mail.template', string="Email Template")
    is_done = fields.Boolean(string="Final Stage")
    fold = fields.Boolean(string="Folded in Kanban")

