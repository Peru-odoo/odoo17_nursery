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
        """
        Prefer the move's secondary UoM; fall back to product template's setting.
        """
        for ml in self:
            sec = ml.move_id.secondary_uom_id
            if not sec and ml.product_id and getattr(ml.product_id.product_tmpl_id, 'is_secondary_uom', False):
                sec = ml.product_id.product_tmpl_id.secondary_uom_id
            ml.secondary_uom_id = sec

    # v17: done quantity field is `quantity`
    @api.depends('quantity', 'product_uom_id', 'secondary_uom_id', 'product_id')
    def _compute_secondary_qty(self):
        """
        Convert the done qty (in ml.product_uom_id) to Secondary UoM.
        - If product primary & secondary are in the same category → use native UoM engine.
        - If categories differ → use product's per‑product factor via product helpers.
        """
        for ml in self:
            tmpl = ml.product_id.product_tmpl_id if ml.product_id else False
            if not (tmpl and getattr(tmpl, 'is_secondary_uom', False) and ml.secondary_uom_id and ml.product_uom_id):
                ml.secondary_qty = 0.0
                continue

            # Normalize done qty into the template's primary UoM
            if tmpl.uom_id and ml.product_uom_id and ml.product_uom_id != tmpl.uom_id:
                primary_in_tmpl_uom = ml.product_uom_id._compute_quantity(ml.quantity or 0.0, tmpl.uom_id)
            else:
                primary_in_tmpl_uom = ml.quantity or 0.0

            # Use product helper to get secondary qty (handles same vs cross category)
            sec = tmpl._to_secondary_qty(primary_in_tmpl_uom)

            ml.secondary_qty = float_round(sec, precision_rounding=ml.secondary_uom_id.rounding or 0.01)
