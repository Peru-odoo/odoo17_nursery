# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools.float_utils import float_round


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    secondary_uom_id = fields.Many2one(
        'uom.uom',
        string='Secondary UOM',
        compute='_compute_secondary_uom',
        store=False,
    )

    secondary_qty = fields.Float(
        string='Secondary Qty',
        digits='Product Unit of Measure',
        compute='_compute_secondary_qty',
        store=False,
    )

    @api.depends('move_id.secondary_uom_id', 'product_id')
    def _compute_secondary_uom(self):
        for ml in self:
            sec = ml.move_id.secondary_uom_id
            if not sec and ml.product_id and getattr(ml.product_id.product_tmpl_id, 'is_secondary_uom', False):
                sec = ml.product_id.product_tmpl_id.secondary_uom_id
            ml.secondary_uom_id = sec

    # v17: use 'quantity' (done quantity on move line)
    @api.depends('quantity', 'product_uom_id', 'secondary_uom_id')
    def _compute_secondary_qty(self):
        for ml in self:
            if ml.secondary_uom_id and ml.product_uom_id:
                src = ml.quantity or 0.0
                qty = ml.product_uom_id._compute_quantity(src, ml.secondary_uom_id)
                ml.secondary_qty = float_round(qty, precision_rounding=ml.secondary_uom_id.rounding or 0.01)
            else:
                ml.secondary_qty = 0.0
