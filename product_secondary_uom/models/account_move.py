# account_move.py
from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    secondary_uom_id = fields.Many2one(related='product_id.secondary_uom_id', readonly=True)
    secondary_qty = fields.Float(string='Secondary Quantity', compute='_compute_secondary_qty', store=True)

    @api.depends('quantity', 'secondary_uom_id')
    def _compute_secondary_qty(self):
        for line in self:
            if line.secondary_uom_id and line.product_uom_id:
                line.secondary_qty = line.quantity / line.secondary_uom_id.factor_inv

