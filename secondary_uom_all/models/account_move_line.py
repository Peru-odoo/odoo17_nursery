# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
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

    # ---------- computes ----------
    @api.depends("product_uom_id")
    def _compute_secondary_category(self):
        for l in self:
            l.secondary_uom_category_id = l.product_uom_id.category_id

    @api.depends("quantity", "product_uom_id", "product_id", "secondary_uom_id")
    def _compute_secondary_qty(self):
        """
        Convert primary -> secondary.
        Normalize line quantity to the product template's primary UoM, then use
        product helpers (same-category via UoM engine, cross-category via factor).
        """
        for l in self:
            tmpl = l.product_id.product_tmpl_id if l.product_id else False
            if not (tmpl and getattr(tmpl, "is_secondary_uom", False) and l.secondary_uom_id and l.product_uom_id):
                l.secondary_qty = 0.0
                continue

            # quantity is in l.product_uom_id; convert to template uom if needed
            if tmpl.uom_id and l.product_uom_id and l.product_uom_id != tmpl.uom_id:
                primary_in_tmpl_uom = l.product_uom_id._compute_quantity(l.quantity or 0.0, tmpl.uom_id)
            else:
                primary_in_tmpl_uom = l.quantity or 0.0

            sec = tmpl._to_secondary_qty(primary_in_tmpl_uom)
            l.secondary_qty = float_round(sec, precision_rounding=l.secondary_uom_id.rounding or 0.01)

    def _inverse_secondary_qty(self):
        """
        Convert edited secondary -> primary.
        Use product helpers, then convert back to the line UoM if needed.
        """
        for l in self:
            tmpl = l.product_id.product_tmpl_id if l.product_id else False
            if not (tmpl and getattr(tmpl, "is_secondary_uom", False) and l.secondary_uom_id and l.product_uom_id):
                continue

            primary_in_tmpl_uom = tmpl._to_primary_qty_from_secondary(l.secondary_qty)

            if tmpl.uom_id and l.product_uom_id and l.product_uom_id != tmpl.uom_id:
                new_primary_in_line_uom = tmpl.uom_id._compute_quantity(primary_in_tmpl_uom, l.product_uom_id)
            else:
                new_primary_in_line_uom = primary_in_tmpl_uom

            rounding = l.product_uom_id.rounding or 0.01
            l.quantity = float_round(new_primary_in_line_uom, precision_rounding=rounding)

    # ---------- onchange ----------
    @api.onchange("product_id")
    def _onchange_product_set_secondary(self):
        for l in self:
            if not l.product_id:
                l.secondary_uom_id = False
                l.secondary_qty = 0.0
                continue
            tmpl = l.product_id.product_tmpl_id
            if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                l.secondary_uom_id = tmpl.secondary_uom_id
                # sync display with current quantity
                l._compute_secondary_qty()
            else:
                l.secondary_uom_id = False
                l.secondary_qty = 0.0

    @api.onchange("secondary_uom_id")
    def _onchange_secondary_uom_id(self):
        for l in self:
            l._compute_secondary_qty()

    # Keep this for manual edits from the UI; delegate to inverse for consistency
    @api.onchange("secondary_qty", "secondary_uom_id", "product_uom_id")
    def _onchange_secondary_qty(self):
        for l in self:
            l._inverse_secondary_qty()

    # ---------- create/write hooks (NEW) ----------
    @api.model_create_multi
    def create(self, vals_list):
        """
        When invoice lines are created from SO/Delivery, onchanges don't run.
        Ensure secondary_uom_id is populated from the product template so
        _compute_secondary_qty() can produce a value.
        """
        for vals in vals_list:
            if not vals.get("secondary_uom_id") and vals.get("product_id"):
                product = self.env["product.product"].browse(vals["product_id"])
                tmpl = product.product_tmpl_id
                if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                    vals["secondary_uom_id"] = tmpl.secondary_uom_id.id
        lines = super().create(vals_list)
        return lines

    def write(self, vals):
        """
        Keep secondary_uom_id aligned when the product changes.
        """
        res = super().write(vals)
        if "product_id" in vals:
            for l in self:
                if not l.product_id:
                    l.secondary_uom_id = False
                    l.secondary_qty = 0.0
                    continue
                tmpl = l.product_id.product_tmpl_id
                if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
                    l.secondary_uom_id = tmpl.secondary_uom_id
                else:
                    l.secondary_uom_id = False
                    l.secondary_qty = 0.0
        return res

    # ---------- constraints ----------
    @api.constrains("secondary_uom_id", "product_uom_id", "product_id")
    def _check_secondary_category_or_factor(self):
        """
        Allow cross-category, but require a positive per-product factor in that case.
        Prevents silent zero/NaN conversions when users choose arbitrary UoMs.
        """
        for l in self:
            if not (l.product_id and l.secondary_uom_id and l.product_uom_id):
                continue
            tmpl = l.product_id.product_tmpl_id
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

# # -*- coding: utf-8 -*-
# from odoo import api, fields, models, _
# from odoo.exceptions import ValidationError
# from odoo.tools.float_utils import float_round
#
#
# class AccountMoveLine(models.Model):
#     _inherit = "account.move.line"
#
#     secondary_uom_category_id = fields.Many2one(
#         "uom.category", compute="_compute_secondary_category", store=False
#     )
#     secondary_uom_id = fields.Many2one(
#         "uom.uom",
#         string="Secondary UOM",
#         help="Secondary unit used for this line.",
#     )
#     secondary_qty = fields.Float(
#         string="Secondary Qty",
#         digits="Product Unit of Measure",
#         compute="_compute_secondary_qty",
#         inverse="_inverse_secondary_qty",
#         store=False,
#     )
#
#     # ---------- computes ----------
#     @api.depends("product_uom_id")
#     def _compute_secondary_category(self):
#         for l in self:
#             l.secondary_uom_category_id = l.product_uom_id.category_id
#
#     @api.depends("quantity", "product_uom_id", "product_id", "secondary_uom_id")
#     def _compute_secondary_qty(self):
#         """
#         Convert primary -> secondary.
#         Normalize line quantity to the product template's primary UoM, then use
#         product helpers (same-category via UoM engine, cross-category via factor).
#         """
#         for l in self:
#             tmpl = l.product_id.product_tmpl_id if l.product_id else False
#             if not (tmpl and getattr(tmpl, "is_secondary_uom", False) and l.secondary_uom_id and l.product_uom_id):
#                 l.secondary_qty = 0.0
#                 continue
#
#             # quantity is in l.product_uom_id; convert to template uom if needed
#             if tmpl.uom_id and l.product_uom_id and l.product_uom_id != tmpl.uom_id:
#                 primary_in_tmpl_uom = l.product_uom_id._compute_quantity(l.quantity or 0.0, tmpl.uom_id)
#             else:
#                 primary_in_tmpl_uom = l.quantity or 0.0
#
#             sec = tmpl._to_secondary_qty(primary_in_tmpl_uom)
#             l.secondary_qty = float_round(sec, precision_rounding=l.secondary_uom_id.rounding or 0.01)
#
#     def _inverse_secondary_qty(self):
#         """
#         Convert edited secondary -> primary.
#         Use product helpers, then convert back to the line UoM if needed.
#         """
#         for l in self:
#             tmpl = l.product_id.product_tmpl_id if l.product_id else False
#             if not (tmpl and getattr(tmpl, "is_secondary_uom", False) and l.secondary_uom_id and l.product_uom_id):
#                 continue
#
#             primary_in_tmpl_uom = tmpl._to_primary_qty_from_secondary(l.secondary_qty)
#
#             if tmpl.uom_id and l.product_uom_id and l.product_uom_id != tmpl.uom_id:
#                 new_primary_in_line_uom = tmpl.uom_id._compute_quantity(primary_in_tmpl_uom, l.product_uom_id)
#             else:
#                 new_primary_in_line_uom = primary_in_tmpl_uom
#
#             rounding = l.product_uom_id.rounding or 0.01
#             l.quantity = float_round(new_primary_in_line_uom, precision_rounding=rounding)
#
#     # ---------- onchange ----------
#     @api.onchange("product_id")
#     def _onchange_product_set_secondary(self):
#         for l in self:
#             if not l.product_id:
#                 l.secondary_uom_id = False
#                 l.secondary_qty = 0.0
#                 continue
#             tmpl = l.product_id.product_tmpl_id
#             if getattr(tmpl, "is_secondary_uom", False) and tmpl.secondary_uom_id:
#                 l.secondary_uom_id = tmpl.secondary_uom_id
#                 # sync display with current quantity
#                 l._compute_secondary_qty()
#             else:
#                 l.secondary_uom_id = False
#                 l.secondary_qty = 0.0
#
#     @api.onchange("secondary_uom_id")
#     def _onchange_secondary_uom_id(self):
#         for l in self:
#             l._compute_secondary_qty()
#
#     # Keep this for manual edits from the UI; delegate to inverse for consistency
#     @api.onchange("secondary_qty", "secondary_uom_id", "product_uom_id")
#     def _onchange_secondary_qty(self):
#         for l in self:
#             l._inverse_secondary_qty()
#
#     # ---------- constraints ----------
#     @api.constrains("secondary_uom_id", "product_uom_id", "product_id")
#     def _check_secondary_category_or_factor(self):
#         """
#         Allow cross-category, but require a positive per-product factor in that case.
#         Prevents silent zero/NaN conversions when users choose arbitrary UoMs.
#         """
#         for l in self:
#             if not (l.product_id and l.secondary_uom_id and l.product_uom_id):
#                 continue
#             tmpl = l.product_id.product_tmpl_id
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
