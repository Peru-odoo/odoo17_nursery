from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class NurseryAdmission(models.Model):
    _name = 'nursery.admission'
    _description = 'Nursery Admission'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    active = fields.Boolean(default=True)

    child_name = fields.Char()
    birth_date = fields.Date()
    gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    application_date = fields.Date(default=fields.Date.today, readonly=True)
    description = fields.Text(string="Notes")
    ####new fields ####################
    allergies = fields.Text()
    medications = fields.Text()
    reason_for_applying = fields.Text()
    parent_email = fields.Char()
    parent_phone = fields.Char()
    parent_mobile = fields.Char()
    parent_type = fields.Selection([('parent', 'Parent'), ('guardian', 'Guardian')])
    parent_gender = fields.Selection([('male', 'Male'), ('female', 'Female')])
    address = fields.Text()
    child_profile = fields.Binary()
    parent_profile = fields.Binary()

    ####new fields ####################


    stage_id = fields.Many2one(
        'nursery.admission.stage',
        string='Stage',
        ondelete='restrict',
        tracking=True,
        store=True,
        copy=False,
        index=True,
    )

    parent_id = fields.Many2one('res.partner', string="Parent")

    def action_accept(self):
        for rec in self:
            rec.status = 'accepted'

    def action_reject(self):
        rejected_stage = self.env['nursery.admission.stage'].search([('name', '=', 'Rejected')], limit=1)
        if not rejected_stage:
            raise ValidationError(_("The 'Rejected' stage was not found. Please create it in the pipeline stages."))
        for rec in self:
            rec.stage_id = rejected_stage.id

    def change_stage(self, stage_id):
        for record in self:
            stage = self.env['nursery.admission.stage'].browse(stage_id)
            record.stage_id = stage
            if stage.email_template_id:
                stage.email_template_id.send_mail(record.id, force_send=True)
