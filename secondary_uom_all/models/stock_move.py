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
        help="Secondary unit used for this move.",
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

    @api.depends("product_uom_qty", "product_uom", "product_id", "secondary_uom_id")
    def _compute_secondary_qty(self):
        for m in self:
            tmpl = m.product_id.product_tmpl_id if m.product_id else False
            # 🔁 ensure secondary_uom_id is set from product if empty
            if not m.secondary_uom_id and tmpl and getattr(tmpl, "is_secondary_uom", False):
                m.secondary_uom_id = tmpl.secondary_uom_id

            if not (tmpl and tmpl.is_secondary_uom and m.secondary_uom_id and m.product_uom):
                m.secondary_qty = 0.0
                continue

            if tmpl.uom_id and m.product_uom and m.product_uom != tmpl.uom_id:
                primary_in_tmpl_uom = m.product_uom._compute_quantity(m.product_uom_qty, tmpl.uom_id)
            else:
                primary_in_tmpl_uom = m.product_uom_qty

            sec = tmpl._to_secondary_qty(primary_in_tmpl_uom)
            m.secondary_qty = float_round(sec, precision_rounding=m.secondary_uom_id.rounding or 0.01)

    def _inverse_secondary_qty(self):
        for m in self:
            tmpl = m.product_id.product_tmpl_id if m.product_id else False
            if not (tmpl and tmpl.is_secondary_uom and m.secondary_uom_id and m.product_uom):
                continue

            primary_in_tmpl_uom = tmpl._to_primary_qty_from_secondary(m.secondary_qty)
            if tmpl.uom_id and m.product_uom and m.product_uom != tmpl.uom_id:
                new_primary_in_move_uom = tmpl.uom_id._compute_quantity(primary_in_tmpl_uom, m.product_uom)
            else:
                new_primary_in_move_uom = primary_in_tmpl_uom

            m.product_uom_qty = float_round(new_primary_in_move_uom, precision_rounding=m.product_uom.rounding or 0.01)

    # 👉 Make sure moves made by the scheduler/flows also get a default secondary UoM
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("secondary_uom_id") and vals.get("product_id"):
                product = self.env["product.product"].browse(vals["product_id"])
                tmpl = product.product_tmpl_id
                if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                    vals["secondary_uom_id"] = tmpl.secondary_uom_id.id
        moves = super().create(vals_list)
        return moves

    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        for m in self:
            tmpl = m.product_id.product_tmpl_id if m.product_id else False
            if tmpl and getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                m.secondary_uom_id = tmpl.secondary_uom_id
                m._compute_secondary_qty()
            else:
                m.secondary_uom_id = False
                m.secondary_qty = 0.0

    @api.onchange("secondary_qty", "secondary_uom_id", "product_uom")
    def _onchange_secondary_qty(self):
        self._inverse_secondary_qty()

    @api.constrains("secondary_uom_id", "product_uom", "product_id")
    def _check_secondary_category_or_factor(self):
        for m in self:
            if not (m.product_id and m.secondary_uom_id and m.product_uom):
                continue
            tmpl = m.product_id.product_tmpl_id
            if not (tmpl and getattr(tmpl, "is_secondary_uom", False) and tmpl.uom_id and tmpl.secondary_uom_id):
                continue
            same_cat = tmpl.uom_id.category_id == tmpl.secondary_uom_id.category_id
            if not same_cat:
                factor = getattr(tmpl, "secondary_conversion_factor", 0.0) or 0.0
                if factor <= 0.0:
                    raise ValidationError(_("Product '%s': cross-category secondary UoM requires a positive "
                                            "'Secondary per 1 Primary' factor on the product.") % (tmpl.display_name,))

# # -*- coding: utf-8 -*-
# from odoo import api, fields, models, _
# from odoo.exceptions import ValidationError
# from odoo.tools.float_utils import float_round
#
#
# class StockMove(models.Model):
#     _inherit = "stock.move"
#
#     # helper (kept for view compatibility)
#     secondary_uom_category_id = fields.Many2one(
#         "uom.category", compute="_compute_secondary_category", store=False
#     )
#
#     secondary_uom_id = fields.Many2one(
#         "uom.uom",
#         string="Secondary UOM",
#         help="Secondary unit used for this move.",
#     )
#
#     secondary_qty = fields.Float(
#         string="Secondary Qty",
#         digits="Product Unit of Measure",
#         compute="_compute_secondary_qty",
#         inverse="_inverse_secondary_qty",
#         store=False,
#     )
#
#     # ---------- computes ----------
#     @api.depends("product_uom")
#     def _compute_secondary_category(self):
#         for m in self:
#             m.secondary_uom_category_id = m.product_uom.category_id
#
#     @api.depends("product_uom_qty", "product_uom", "product_id", "secondary_uom_id")
#     def _compute_secondary_qty(self):
#         """
#         Convert primary -> secondary.
#         If move UoM != template UoM, normalize to template first, then use product helpers
#         (which handle same-category via Odoo UoM engine and cross-category via factor).
#         """
#         for m in self:
#             tmpl = m.product_id.product_tmpl_id if m.product_id else False
#             if not (tmpl and tmpl.is_secondary_uom and m.secondary_uom_id and m.product_uom):
#                 m.secondary_qty = 0.0
#                 continue
#
#             # normalize primary qty to template's primary UoM
#             if tmpl.uom_id and m.product_uom and m.product_uom != tmpl.uom_id:
#                 primary_in_tmpl_uom = m.product_uom._compute_quantity(m.product_uom_qty, tmpl.uom_id)
#             else:
#                 primary_in_tmpl_uom = m.product_uom_qty
#
#             # product helper -> secondary
#             sec = tmpl._to_secondary_qty(primary_in_tmpl_uom)
#
#             m.secondary_qty = float_round(sec, precision_rounding=m.secondary_uom_id.rounding or 0.01)
#
#     def _inverse_secondary_qty(self):
#         """
#         Convert edited secondary -> primary.
#         Use product helpers for category awareness, then convert from template UoM to move UoM if needed.
#         """
#         for m in self:
#             tmpl = m.product_id.product_tmpl_id if m.product_id else False
#             if not (tmpl and tmpl.is_secondary_uom and m.secondary_uom_id and m.product_uom):
#                 continue
#
#             # secondary -> template primary
#             primary_in_tmpl_uom = tmpl._to_primary_qty_from_secondary(m.secondary_qty)
#
#             # template primary -> move UoM
#             if tmpl.uom_id and m.product_uom and m.product_uom != tmpl.uom_id:
#                 new_primary_in_move_uom = tmpl.uom_id._compute_quantity(primary_in_tmpl_uom, m.product_uom)
#             else:
#                 new_primary_in_move_uom = primary_in_tmpl_uom
#
#             m.product_uom_qty = float_round(new_primary_in_move_uom, precision_rounding=m.product_uom.rounding or 0.01)
#
#     # ---------- onchange ----------
#     @api.onchange("product_id")
#     def _onchange_product_set_secondary(self):
#         for m in self:
#             tmpl = m.product_id.product_tmpl_id if m.product_id else False
#             if tmpl and getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
#                 m.secondary_uom_id = tmpl.secondary_uom_id
#                 # sync display
#                 m._compute_secondary_qty()
#             else:
#                 m.secondary_uom_id = False
#                 m.secondary_qty = 0.0
#
#     # Keep this onchange for manual edits on secondary fields (UI typing)
#     @api.onchange("secondary_qty", "secondary_uom_id", "product_uom")
#     def _onchange_secondary_qty(self):
#         for m in self:
#             # Delegate to inverse to avoid duplication
#             self._inverse_secondary_qty()
#
#     # ---------- constraints ----------
#     @api.constrains("secondary_uom_id", "product_uom", "product_id")
#     def _check_secondary_category_or_factor(self):
#         """
#         Allow cross-category, but require a positive per-product factor in that case.
#         Prevents silent zero/NaN conversions when users choose arbitrary UoMs.
#         """
#         for m in self:
#             if not (m.product_id and m.secondary_uom_id and m.product_uom):
#                 continue
#             tmpl = m.product_id.product_tmpl_id
#             if not (tmpl and getattr(tmpl, "is_secondary_uom", False) and tmpl.uom_id and tmpl.secondary_uom_id):
#                 continue
#
#             same_cat = tmpl.uom_id.category_id == tmpl.secondary_uom_id.category_id
#             if not same_cat:
#                 factor = getattr(tmpl, "secondary_conversion_factor", 0.0) or 0.0
#                 if factor <= 0.0:
#                     raise ValidationError(_(
#                         "Product '%s': cross-category secondary UoM requires a positive "
#                         "'Secondary per 1 Primary' factor on the product."
#                     ) % (tmpl.display_name,))
