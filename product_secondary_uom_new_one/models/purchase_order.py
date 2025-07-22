from odoo import models, fields, api

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    secondary_qty = fields.Float(
        string='Secondary Quantity',
        compute='_compute_secondary_qty',
        inverse='_inverse_secondary_qty',
        store=True,
        readonly=False
    )

    secondary_uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string="Secondary UOM",
        domain="[('uom_type', '=', 'reference')]"
    )

    @api.depends('product_qty', 'product_uom', 'secondary_uom_id')
    def _compute_secondary_qty(self):
        for line in self:
            if line.secondary_uom_id and line.product_uom:
                factor = line.secondary_uom_id.factor_inv / line.product_uom.factor_inv
                line.secondary_qty = line.product_qty / factor if factor else 0.0
            else:
                line.secondary_qty = 0.0

    def _inverse_secondary_qty(self):
        for line in self:
            if line.secondary_uom_id and line.product_uom:
                factor = line.secondary_uom_id.factor_inv / line.product_uom.factor_inv
                line.product_qty = line.secondary_qty * factor if factor else 0.0





# from odoo import models, fields, api
#
# class PurchaseOrderLine(models.Model):
#     _inherit = 'purchase.order.line'
#
#     is_secondary_uom = fields.Boolean(
#         related='product_id.product_tmpl_id.is_secondary_uom',
#         readonly=True
#     )
#     secondary_uom_id = fields.Many2one(
#         'uom.uom',
#         related='product_id.product_tmpl_id.secondary_uom_id',
#         readonly=True
#     )
#     secondary_qty = fields.Float(
#         string='Secondary Qty',
#         compute='_compute_secondary_qty',
#         readonly=True
#     )
#
#     @api.depends('product_qty', 'secondary_uom_id')
#     def _compute_secondary_qty(self):
#         for line in self:
#             if line.secondary_uom_id and line.secondary_uom_id.factor_inv:
#                 line.secondary_qty = line.product_qty / line.secondary_uom_id.factor_inv
#             else:
#                 line.secondary_qty = 0.0
