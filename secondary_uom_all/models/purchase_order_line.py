# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools.float_utils import float_round


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # helper for domain in views
    secondary_uom_category_id = fields.Many2one(
        "uom.category",
        compute="_compute_secondary_category",
        store=False,
    )

    # secondary UoM chosen for the line
    secondary_uom_id = fields.Many2one(
        "uom.uom",
        string="Secondary UOM",
        help="Secondary unit used for this line.",
    )

    # qty shown/edited depending on the toggle
    secondary_qty = fields.Float(
        string="Secondary Qty",
        digits="Product Unit of Measure",
    )

    # user selects which side is the input source
    use_secondary_input = fields.Boolean(
        string="Enter in Secondary UoM",
        help="If enabled, you enter the quantity in Secondary UoM and the primary"
             " Quantity is computed; otherwise you enter the primary Quantity"
             " and the Secondary Qty is computed.",
        default=False,
    )

    # --- computes / defaults ---

    @api.depends("product_uom")
    def _compute_secondary_category(self):
        for line in self:
            line.secondary_uom_category_id = line.product_uom.category_id

    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        """Default the secondary UoM from the product template."""
        for line in self:
            if not line.product_id:
                line.secondary_uom_id = False
                line.secondary_qty = 0.0
                continue
            tmpl = line.product_id.product_tmpl_id
            if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                line.secondary_uom_id = tmpl.secondary_uom_id
            else:
                line.secondary_uom_id = False
                line.secondary_qty = 0.0
        # also recompute display so the grid looks right
        self._onchange_primary_to_secondary()

    # --- synchronization without feedback loops ---

    @api.onchange("product_qty", "product_uom", "secondary_uom_id")
    def _onchange_primary_to_secondary(self):
        """User edits primary -> recompute secondary (only if toggle is OFF)."""
        for line in self:
            if line.use_secondary_input:
                # when editing in secondary, don't override user's input
                continue
            if line.secondary_uom_id and line.product_uom:
                line.secondary_qty = line.product_uom._compute_quantity(
                    line.product_qty, line.secondary_uom_id
                )
            else:
                line.secondary_qty = 0.0

    @api.onchange("secondary_qty", "secondary_uom_id")
    def _onchange_secondary_to_primary(self):
        """User edits secondary -> recompute primary (only if toggle is ON)."""
        for line in self:
            if not line.use_secondary_input:
                # when editing in primary, don't override user's input
                continue
            if line.secondary_uom_id and line.product_uom:
                qty = line.secondary_uom_id._compute_quantity(
                    line.secondary_qty, line.product_uom
                )
                rounding = line.product_uom.rounding or 0.01
                line.product_qty = float_round(qty, precision_rounding=rounding)

    @api.onchange("use_secondary_input")
    def _onchange_use_secondary_input(self):
        """When the user flips the toggle, convert once to keep values aligned."""
        for line in self:
            if line.secondary_uom_id and line.product_uom:
                if line.use_secondary_input:
                    # switching to secondary input -> prefill secondary from primary
                    line.secondary_qty = line.product_uom._compute_quantity(
                        line.product_qty, line.secondary_uom_id
                    )
                else:
                    # switching to primary input -> prefill primary from secondary
                    qty = line.secondary_uom_id._compute_quantity(
                        line.secondary_qty, line.product_uom
                    )
                    rounding = line.product_uom.rounding or 0.01
                    line.product_qty = float_round(qty, precision_rounding=rounding)
