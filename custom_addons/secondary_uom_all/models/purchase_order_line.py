# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # helper for domain in views (kept for compatibility)
    secondary_uom_category_id = fields.Many2one(
        "uom.category",
        compute="_compute_secondary_category",
        store=False,
    )

    # secondary UoM chosen for the line
    secondary_uom_id = fields.Many2one(
        "uom.uom",
        string="Secondary UOM",
        help="Secondary unit used for this line."
    )

    # qty shown/edited depending on the toggle
    secondary_qty = fields.Float(
        string="Secondary Qty",
        digits="Product Unit of Measure",
    )

    # user selects which side is the input source
    use_secondary_input = fields.Boolean(
        string="Enter in Secondary UoM",
        help=(
            "If enabled, you enter the quantity in Secondary UoM and the primary "
            "Quantity is computed; otherwise you enter the primary Quantity "
            "and the Secondary Qty is computed."
        ),
        default=False,
    )

    # --- computes / defaults ---

    @api.depends("product_uom")
    def _compute_secondary_category(self):
        for line in self:
            line.secondary_uom_category_id = line.product_uom.category_id

    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        """Default the secondary UoM from the product template and sync qty."""
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
        """
        User edits primary -> recompute secondary (only if toggle is OFF).
        Handles both same-category and cross-category via product template helpers.
        """
        for line in self:
            if line.use_secondary_input:
                # when editing in secondary, don't override user's input
                continue

            tmpl = line.product_id.product_tmpl_id if line.product_id else False
            if not (tmpl and line.secondary_uom_id and line.product_uom):
                line.secondary_qty = 0.0
                continue

            # Convert line.product_qty (in line.product_uom) -> template primary UoM
            if tmpl.uom_id and line.product_uom and line.product_uom != tmpl.uom_id:
                primary_in_tmpl_uom = line.product_uom._compute_quantity(line.product_qty, tmpl.uom_id)
            else:
                primary_in_tmpl_uom = line.product_qty

            # Then template helper -> secondary
            line.secondary_qty = tmpl._to_secondary_qty(primary_in_tmpl_uom)

    @api.onchange("secondary_qty", "secondary_uom_id")
    def _onchange_secondary_to_primary(self):
        """
        User edits secondary -> recompute primary (only if toggle is ON).
        Handles both same-category and cross-category via product template helpers.
        """
        for line in self:
            if not line.use_secondary_input:
                # when editing in primary, don't override user's input
                continue

            tmpl = line.product_id.product_tmpl_id if line.product_id else False
            if not (tmpl and line.secondary_uom_id and line.product_uom):
                continue

            # Convert secondary -> template primary UoM
            primary_in_tmpl_uom = tmpl._to_primary_qty_from_secondary(line.secondary_qty)

            # Convert template primary UoM -> line.product_uom if needed
            if tmpl.uom_id and line.product_uom and line.product_uom != tmpl.uom_id:
                new_primary_in_line_uom = tmpl.uom_id._compute_quantity(primary_in_tmpl_uom, line.product_uom)
            else:
                new_primary_in_line_uom = primary_in_tmpl_uom

            rounding = line.product_uom.rounding or 0.01
            line.product_qty = float_round(new_primary_in_line_uom, precision_rounding=rounding)

    @api.onchange("use_secondary_input")
    def _onchange_use_secondary_input(self):
        """
        When the user flips the toggle, convert once to keep values aligned.
        Uses product template helpers to support cross-category.
        """
        for line in self:
            tmpl = line.product_id.product_tmpl_id if line.product_id else False
            if not (tmpl and line.secondary_uom_id and line.product_uom):
                continue

            if line.use_secondary_input:
                # switching to secondary input -> prefill secondary from primary
                if tmpl.uom_id and line.product_uom and line.product_uom != tmpl.uom_id:
                    primary_in_tmpl_uom = line.product_uom._compute_quantity(line.product_qty, tmpl.uom_id)
                else:
                    primary_in_tmpl_uom = line.product_qty
                line.secondary_qty = tmpl._to_secondary_qty(primary_in_tmpl_uom)
            else:
                # switching to primary input -> prefill primary from secondary
                primary_in_tmpl_uom = tmpl._to_primary_qty_from_secondary(line.secondary_qty)
                if tmpl.uom_id and line.product_uom and line.product_uom != tmpl.uom_id:
                    new_primary_in_line_uom = tmpl.uom_id._compute_quantity(primary_in_tmpl_uom, line.product_uom)
                else:
                    new_primary_in_line_uom = primary_in_tmpl_uom

                rounding = line.product_uom.rounding or 0.01
                line.product_qty = float_round(new_primary_in_line_uom, precision_rounding=rounding)

    # --- constraints ---

    @api.constrains("secondary_uom_id", "product_uom", "product_id")
    def _check_secondary_category_or_factor(self):
        """
        If categories differ, ensure the product has a positive cross-category factor.
        Prevents silent zero/NaN conversions when users pick arbitrary UoMs.
        """
        for line in self:
            if not (line.product_id and line.secondary_uom_id and line.product_uom):
                continue
            tmpl = line.product_id.product_tmpl_id
            if not (tmpl and getattr(tmpl, "is_secondary_uom", False) and tmpl.uom_id and tmpl.secondary_uom_id):
                continue

            same_cat = tmpl.uom_id.category_id == tmpl.secondary_uom_id.category_id
            if not same_cat:
                factor = getattr(tmpl, "secondary_conversion_factor", 0.0) or 0.0
                if factor <= 0.0:
                    raise ValidationError(_(
                        "Product '%s': cross-category secondary UoM requires a positive "
                        "'Secondary per 1 Primary' factor on the product."
                    ) % (tmpl.display_name,))
