from odoo import models, fields

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    application_date = fields.Date(string="Application Date")
    parent_id = fields.Many2one('res.partner', string="Parent Name")
    child_name = fields.Char(string="Child Name")
    application_status = fields.Selection([
        ('applied', 'Applied'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ], string="Status")
    submitted_documents = fields.Binary(string="Submitted Documents")
