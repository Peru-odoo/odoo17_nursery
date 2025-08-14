from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    # helper: the UoM category of the primary UoM (needed for the domain in v17)
    secondary_uom_category_id = fields.Many2one(
        "uom.category", compute="_compute_secondary_category", store=False
    )

    # secondary UoM and quantity (bi-directional with the primary)
    secondary_uom_id = fields.Many2one(
        "uom.uom", string="Secondary UOM",
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

    @api.depends("product_uom_qty", "product_uom", "secondary_uom_id")
    def _compute_secondary_qty(self):
        for line in self:
            if line.secondary_uom_id and line.product_uom:
                line.secondary_qty = line.product_uom._compute_quantity(
                    line.product_uom_qty, line.secondary_uom_id
                )
            else:
                line.secondary_qty = 0.0

    def _inverse_secondary_qty(self):
        for line in self:
            if line.secondary_uom_id and line.product_uom:
                line.product_uom_qty = line.secondary_uom_id._compute_quantity(
                    line.secondary_qty, line.product_uom
                )

    # default secondary UoM from product template
    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        for line in self:
            if not line.product_id:
                line.secondary_uom_id = False
                continue
            tmpl = line.product_id.product_tmpl_id
            if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                line.secondary_uom_id = tmpl.secondary_uom_id
            else:
                line.secondary_uom_id = False
