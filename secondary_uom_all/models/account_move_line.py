# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools.float_utils import float_round


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    secondary_uom_category_id = fields.Many2one(
        "uom.category", compute="_compute_secondary_category", store=False
    )
    secondary_uom_id = fields.Many2one(
        "uom.uom",
        string="Secondary UOM",
        help="Secondary unit used for this line.",
    )
    secondary_qty = fields.Float(
        string="Secondary Qty",
        digits="Product Unit of Measure",
        compute="_compute_secondary_qty",
        inverse="_inverse_secondary_qty",
        store=False,
    )

    @api.depends("product_uom_id")
    def _compute_secondary_category(self):
        for l in self:
            l.secondary_uom_category_id = l.product_uom_id.category_id

    @api.depends("quantity", "product_uom_id", "secondary_uom_id")
    def _compute_secondary_qty(self):
        for l in self:
            if l.secondary_uom_id and l.product_uom_id:
                qty = l.product_uom_id._compute_quantity(l.quantity, l.secondary_uom_id)
                l.secondary_qty = float_round(qty, precision_rounding=l.secondary_uom_id.rounding or 0.01)
            else:
                l.secondary_qty = 0.0

    def _inverse_secondary_qty(self):
        for l in self:
            if l.secondary_uom_id and l.product_uom_id:
                qty = l.secondary_uom_id._compute_quantity(l.secondary_qty, l.product_uom_id)
                l.quantity = float_round(qty, precision_rounding=l.product_uom_id.rounding or 0.01)

    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        for l in self:
            tmpl = l.product_id.product_tmpl_id
            if tmpl and getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                l.secondary_uom_id = tmpl.secondary_uom_id
            else:
                l.secondary_uom_id = False
                l.secondary_qty = 0.0

    # add below _inverse_secondary_qty(...)
    @api.onchange("secondary_qty", "secondary_uom_id", "product_uom_id")
    def _onchange_secondary_qty(self):
        for l in self:
            if l.secondary_uom_id and l.product_uom_id:
                qty = l.secondary_uom_id._compute_quantity(l.secondary_qty, l.product_uom_id)
                rounding = l.product_uom_id.rounding or 0.01
                l.quantity = float_round(qty, precision_rounding=rounding)

