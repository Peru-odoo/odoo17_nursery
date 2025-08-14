from odoo import models, api, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Skip check for purchase receipts (incoming stock)
        if self.picking_type_id.code == 'incoming':
            return super(StockPicking, self).button_validate()

        for picking in self:
            for move in picking.move_ids_without_package:
                product = move.product_id
                location = move.location_id

                # Only check for storable products
                if product.type != 'product':
                    continue

                # Respect the checkbox on the location
                if getattr(location, 'allow_negative_stock', False):
                    continue

                # Get available quantity for that location
                qty_available = product.with_context(location=location.id).qty_available
                requested_qty = move.product_uom_qty

                # Block if insufficient stock
                if qty_available < requested_qty:
                    raise UserError(_(
                        "Invalid Operation:\n"
                        "You cannot validate this operation.\n"
                        "Product '%s' would go into negative stock.\n"
                        "Available: %s, Requested: %s"
                    ) % (product.display_name, qty_available, requested_qty))

        return super(StockPicking, self).button_validate()


# from odoo import models, _
# from odoo.exceptions import UserError
#
# class StockPicking(models.Model):
#     _inherit = 'stock.picking'
#
#     def button_validate(self):
#         for picking in self:
#             for move in picking.move_ids_without_package:
#                 # Skip non-stockable products
#                 if move.product_id.type != 'product':
#                     continue
#
#                 # Check if source location allows negative stock
#                 location = move.location_id
#                 if hasattr(location, 'allow_negative_stock') and location.allow_negative_stock:
#                     # If warehouse/location allows negative stock, skip this check
#                     continue
#
#                 available_qty = move.product_id.qty_available
#                 requested_qty = move.product_uom_qty
#
#                 # Block only if requested qty > available stock
#                 if requested_qty > available_qty:
#                     raise UserError(_(
#                         "You cannot validate this delivery.\n"
#                         "Product '%s' would go into negative stock.\n"
#                         "Available: %s, Requested: %s"
#                     ) % (move.product_id.display_name, available_qty, requested_qty))
#
#         return super(StockPicking, self).button_validate()

# from odoo import models, _
# from odoo.exceptions import UserError
#
# class StockPicking(models.Model):
#     _inherit = 'stock.picking'
#
#     def button_validate(self):
#         for picking in self:
#             for move in picking.move_ids_without_package:
#                 # Skip non-stockable products
#                 if move.product_id.type != 'product':
#                     continue
#
#                 available_qty = move.product_id.qty_available
#                 requested_qty = move.product_uom_qty
#
#                 # Check if more than available stock
#                 if requested_qty > available_qty:
#                     raise UserError(_(
#                         "You cannot validate this delivery.\n"
#                         "Product '%s' would go into negative stock.\n"
#                         "Available: %s, Requested: %s"
#                     ) % (move.product_id.display_name, available_qty, requested_qty))
#
#         # If all checks pass, proceed with the normal validation
#         return super(StockPicking, self).button_validate()
#
# # from odoo import models, _
# # from odoo.exceptions import UserError
# #
# # class StockPicking(models.Model):
# #     _inherit = 'stock.picking'
# #
# #     def _check_negative_stock_before_validate(self):
# #         """Run before validation or backorder popup."""
# #         for picking in self:
# #             if picking.picking_type_code == 'outgoing':
# #                 for move in picking.move_ids_without_package:
# #                     product = move.product_id
# #                     qty_available = product.qty_available
# #                     qty_done = sum(line.qty_done for line in move.move_line_ids)
# #                     location = move.location_id
# #                     allow_negative = getattr(location, 'allow_negative', False)
# #
# #                     if not allow_negative:
# #                         if qty_done > qty_available:
# #                             raise UserError(_(
# #                                 "You cannot validate this delivery.\n"
# #                                 "Product '%s' would go into negative stock.\n"
# #                                 "Available: %.2f, Requested: %.2f"
# #                             ) % (product.display_name, qty_available, qty_done))
# #         return True
# #
# #     def button_validate(self):
# #         # Run our check BEFORE Odoo shows backorder popup
# #         self._check_negative_stock_before_validate()
# #
# #         # Continue with normal validation
# #         return super(StockPicking, self).button_validate()
