from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    secondary_qty_available = fields.Float(
        string="On Hand Dozens",
        compute="_compute_secondary_qtys",
        store=False,
    )
    secondary_virtual_available = fields.Float(
        string="Forecasted Dozens",
        compute="_compute_secondary_qtys",
        store=False,
    )

    @api.depends('qty_available', 'virtual_available', 'uom_id', 'secondary_uom_id')
    def _compute_secondary_qtys(self):
        for product in self:
            if product.secondary_uom_id and product.secondary_uom_id.factor_inv:
                factor = product.secondary_uom_id.factor_inv
                product.secondary_qty_available = product.qty_available / factor
                product.secondary_virtual_available = product.virtual_available / factor
            else:
                product.secondary_qty_available = 0.0
                product.secondary_virtual_available = 0.0

    def action_show_secondary_onhand(self):
        return {
            'name': 'Stock Quants (Secondary)',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.quant',
            'view_mode': 'tree,form',
            'domain': [('product_id.product_tmpl_id', 'in', self.ids)],
            'context': {
                'search_default_group_by_location': 1,
            },
        }

    def action_show_secondary_forecast(self):
        return {
            'name': 'Forecasted Stock (Secondary)',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.quant',
            'view_mode': 'tree,form',
            'domain': [('product_id.product_tmpl_id', 'in', self.ids)],
        }


# from odoo import models, fields, api
#
# class ProductTemplate(models.Model):
#     _inherit = 'product.template'
#
#     secondary_qty_available = fields.Float(
#         string="On Hand Dozens",
#         compute="_compute_secondary_qtys",
#         store=False,
#     )
#     secondary_virtual_available = fields.Float(
#         string="Forecasted Dozens",
#         compute="_compute_secondary_qtys",
#         store=False,
#     )
#
#     @api.depends('qty_available', 'virtual_available', 'uom_id', 'secondary_uom_id')
#     def _compute_secondary_qtys(self):
#         for product in self:
#             if product.secondary_uom_id and product.secondary_uom_id.factor_inv:
#                 factor = product.secondary_uom_id.factor_inv
#                 product.secondary_qty_available = product.qty_available / factor
#                 product.secondary_virtual_available = product.virtual_available / factor
#             else:
#                 product.secondary_qty_available = 0.0
#                 product.secondary_virtual_available = 0.0
#
#     def action_cost_structure(self):
#         """Dummy method to prevent validation error"""
#         return True
