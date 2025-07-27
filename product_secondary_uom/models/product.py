from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_secondary_uom = fields.Boolean(string='Is Secondary Unit?')
    secondary_uom_id = fields.Many2one('uom.uom', string='Secondary UOM')
    secondary_uom_factor = fields.Float(
        string='Secondary UoM Factor',
        compute='_compute_secondary_uom_factor',
        store=True,
        readonly=True,
    )

    @api.depends('secondary_uom_id')
    def _compute_secondary_uom_factor(self):
        for product in self:
            product.secondary_uom_factor = product.secondary_uom_id.factor_inv if product.secondary_uom_id else 0.0
