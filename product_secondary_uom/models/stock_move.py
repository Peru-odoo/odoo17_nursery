from odoo import models, fields, api

class StockMove(models.Model):
    _inherit = 'stock.move'

    secondary_uom_id = fields.Many2one(related='product_id.secondary_uom_id', readonly=True, store=True)
    secondary_qty = fields.Float(string='Secondary Quantity', compute='_compute_secondary_qty', store=True)

    @api.depends('product_uom_qty', 'product_id.secondary_uom_id')
    def _compute_secondary_qty(self):
        for move in self:
            if move.product_id.secondary_uom_id:
                ratio = 1.0 / move.product_id.secondary_uom_id.factor_inv
                move.secondary_qty = move.product_uom_qty * ratio
