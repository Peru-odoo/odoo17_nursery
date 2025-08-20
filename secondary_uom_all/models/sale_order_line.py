from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # Kept for view compatibility (not strictly needed if you allow cross-category)
    secondary_uom_category_id = fields.Many2one(
        "uom.category", compute="_compute_secondary_category", store=False
    )

    # Secondary UoM & quantity (bi-directional with the primary)
    secondary_uom_id = fields.Many2one(
        "uom.uom",
        string="Secondary UOM",
        help="Secondary unit used for this line."
    )
    secondary_qty = fields.Float(
        string="Secondary Qty",
        digits="Product Unit of Measure",
        compute="_compute_secondary_qty",
        inverse="_inverse_secondary_qty",
        store=False,
    )

    # ---------- computes ----------
    @api.depends("product_uom")
    def _compute_secondary_category(self):
        for line in self:
            line.secondary_uom_category_id = line.product_uom.category_id

    @api.depends(
        "product_uom_qty",
        "product_uom",
        "product_id",
        "secondary_uom_id",
    )
    def _compute_secondary_qty(self):
        """Compute secondary_qty from primary, handling same- and cross-category cases."""
        for line in self:
            tmpl = line.product_id.product_tmpl_id if line.product_id else False
            if not (tmpl and tmpl.is_secondary_uom and line.secondary_uom_id and line.product_uom):
                line.secondary_qty = 0.0
                continue

            # Step 1: express current primary qty in the template's primary UoM
            if tmpl.uom_id and line.product_uom and line.product_uom != tmpl.uom_id:
                primary_in_tmpl_uom = line.product_uom._compute_quantity(line.product_uom_qty, tmpl.uom_id)
            else:
                primary_in_tmpl_uom = line.product_uom_qty

            # Step 2: convert to secondary via product helper (handles categories + factor)
            line.secondary_qty = tmpl._to_secondary_qty(primary_in_tmpl_uom)

    def _inverse_secondary_qty(self):
        """Write back product_uom_qty after editing secondary_qty."""
        for line in self:
            tmpl = line.product_id.product_tmpl_id if line.product_id else False
            if not (tmpl and tmpl.is_secondary_uom and line.secondary_uom_id and line.product_uom):
                continue

            # Step 1: convert edited secondary -> primary in template uom
            primary_in_tmpl_uom = tmpl._to_primary_qty_from_secondary(line.secondary_qty)

            # Step 2: convert from template uom -> line uom if needed
            if tmpl.uom_id and line.product_uom and line.product_uom != tmpl.uom_id:
                new_primary_in_line_uom = tmpl.uom_id._compute_quantity(primary_in_tmpl_uom, line.product_uom)
            else:
                new_primary_in_line_uom = primary_in_tmpl_uom

            line.product_uom_qty = new_primary_in_line_uom

    # ---------- onchange ----------
    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        """Default secondary UoM from product template; sync qty."""
        for line in self:
            if not line.product_id:
                line.secondary_uom_id = False
                line.secondary_qty = 0.0
                continue

            tmpl = line.product_id.product_tmpl_id
            if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                line.secondary_uom_id = tmpl.secondary_uom_id
                # Recompute secondary based on current primary qty
                line._compute_secondary_qty()
            else:
                line.secondary_uom_id = False
                line.secondary_qty = 0.0

    @api.onchange("secondary_uom_id")
    def _onchange_secondary_uom_id_recompute(self):
        """If user changes the secondary UoM, recompute the secondary qty."""
        for line in self:
            line._compute_secondary_qty()

    # ---------- constraints ----------
    @api.constrains("secondary_uom_id", "product_uom", "product_id")
    def _check_secondary_category_or_factor(self):
        """If categories differ, ensure product has a positive cross-category factor."""
        for line in self:
            if not (line.product_id and line.secondary_uom_id and line.product_uom):
                continue
            tmpl = line.product_id.product_tmpl_id
            if not (tmpl and tmpl.is_secondary_uom and tmpl.secondary_uom_id and tmpl.uom_id):
                continue

            same_cat = tmpl.uom_id.category_id == tmpl.secondary_uom_id.category_id
            if not same_cat:
                factor = tmpl.secondary_conversion_factor or 0.0
                if factor <= 0.0:
                    raise ValidationError(_(
                        "Product '%s': cross-category secondary UoM requires a positive "
                        "'Secondary per 1 Primary' factor on the product."
                    ) % (tmpl.display_name,))
