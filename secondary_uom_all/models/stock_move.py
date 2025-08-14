# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round


class StockMove(models.Model):
    _inherit = "stock.move"

    secondary_uom_category_id = fields.Many2one(
        "uom.category", compute="_compute_secondary_category", store=False
    )
    secondary_uom_id = fields.Many2one(
        "uom.uom",
        string="Secondary UOM",
        help="Secondary unit used for this move (same category as UoM).",
    )
    secondary_qty = fields.Float(
        string="Secondary Qty",
        digits="Product Unit of Measure",
        compute="_compute_secondary_qty",
        inverse="_inverse_secondary_qty",
        store=False,
    )

    @api.depends("product_uom")
    def _compute_secondary_category(self):
        for m in self:
            m.secondary_uom_category_id = m.product_uom.category_id

    @api.depends("product_uom_qty", "product_uom", "secondary_uom_id")
    def _compute_secondary_qty(self):
        for m in self:
            if m.secondary_uom_id and m.product_uom:
                qty = m.product_uom._compute_quantity(m.product_uom_qty, m.secondary_uom_id)
                m.secondary_qty = float_round(qty, precision_rounding=m.secondary_uom_id.rounding or 0.01)
            else:
                m.secondary_qty = 0.0

    def _inverse_secondary_qty(self):
        for m in self:
            if m.secondary_uom_id and m.product_uom:
                qty = m.secondary_uom_id._compute_quantity(m.secondary_qty, m.product_uom)
                m.product_uom_qty = float_round(qty, precision_rounding=m.product_uom.rounding or 0.01)

    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        for m in self:
            tmpl = m.product_id.product_tmpl_id
            if tmpl and getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                m.secondary_uom_id = tmpl.secondary_uom_id
            else:
                m.secondary_uom_id = False
                m.secondary_qty = 0.0

    @api.constrains("secondary_uom_id", "product_uom")
    def _check_secondary_category(self):
        for m in self:
            if m.secondary_uom_id and m.product_uom and \
               m.secondary_uom_id.category_id != m.product_uom.category_id:
                raise ValidationError(_("Secondary UOM must be in the same category as the primary UoM."))

    # add below _inverse_secondary_qty(...)
    @api.onchange("secondary_qty", "secondary_uom_id", "product_uom")
    def _onchange_secondary_qty(self):
        for m in self:
            if m.secondary_uom_id and m.product_uom:
                qty = m.secondary_uom_id._compute_quantity(m.secondary_qty, m.product_uom)
                rounding = m.product_uom.rounding or 0.01
                m.product_uom_qty = float_round(qty, precision_rounding=rounding)

