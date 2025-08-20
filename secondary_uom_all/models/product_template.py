from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_round, float_is_zero


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # --- Feature toggle + secondary UoM selection ---
    is_secondary_uom = fields.Boolean(
        string="Is Secondary Unit?",
        help="Enable to use a secondary unit of measure for this product.",
    )
    secondary_uom_id = fields.Many2one(
        'uom.uom',
        string="Secondary UOM",
        help="Select the secondary unit of measure. "
             "If it's not in the same category as the Primary UoM, a conversion factor is required.",
    )

    # Helper for safe domain use in v17 views (kept from your code)
    secondary_uom_category_id = fields.Many2one(
        'uom.category',
        compute='_compute_sec_cat',
        string="UoM Category (Helper)",
    )

    # Helper to print the unit name (kept from your code)
    secondary_uom_name = fields.Char(
        string="Secondary UoM Name",
        compute="_compute_secondary_uom_name",
        store=False,
    )

    # --- NEW: Cross-category handling ---
    secondary_conversion_factor = fields.Float(
        string="Secondary per 1 Primary",
        help=(
            "How many Secondary units equal ONE Primary unit. "
            "Used ONLY when Primary and Secondary UoMs are in DIFFERENT categories.\n"
            "Example: If 1 kg = 0.02 box, set this to 0.02."
        ),
        digits='Product Unit of Measure',
        default=1.0,
    )

    secondary_cross_category = fields.Boolean(
        string="Secondary in Different Category",
        compute='_compute_secondary_cross_category',
        store=False,
    )

    # --- Quantities in secondary (shown on product header) ---
    qty_on_hand_secondary = fields.Float(
        string="On Hand (Secondary UOM)",
        compute="_compute_secondary_quantities",
        digits='Product Unit of Measure',
    )
    qty_forecasted_secondary = fields.Float(
        string="Forecasted (Secondary UOM)",
        compute="_compute_secondary_quantities",
        digits='Product Unit of Measure',
    )

    # Labels for header buttons (kept, but now aware of cross-category)
    qty_on_hand_secondary_label = fields.Char(compute="_compute_sec_labels", store=False)
    qty_forecasted_secondary_label = fields.Char(compute="_compute_sec_labels", store=False)

    # -------------------- COMPUTES --------------------
    @api.depends('uom_id')
    def _compute_sec_cat(self):
        for rec in self:
            rec.secondary_uom_category_id = rec.uom_id.category_id

    @api.depends('secondary_uom_id')
    def _compute_secondary_uom_name(self):
        for rec in self:
            rec.secondary_uom_name = rec.secondary_uom_id.name or ''

    @api.depends('uom_id', 'secondary_uom_id', 'is_secondary_uom')
    def _compute_secondary_cross_category(self):
        for p in self:
            p.secondary_cross_category = bool(
                p.is_secondary_uom
                and p.secondary_uom_id
                and p.uom_id
                and p.secondary_uom_id.category_id != p.uom_id.category_id
            )

    # Centralized helpers so other models (SO/PO/Stock/Accounting) can reuse consistently
    def _to_secondary_qty(self, primary_qty):
        """Convert primary_qty (in template's primary UoM) -> secondary_qty based on product config."""
        self.ensure_one()
        if not (self.is_secondary_uom and self.secondary_uom_id and self.uom_id):
            return 0.0

        # Same category -> use Odoo UoM engine
        if self.uom_id.category_id == self.secondary_uom_id.category_id:
            return self.uom_id._compute_quantity(primary_qty, self.secondary_uom_id)

        # Cross category -> manual factor
        return primary_qty * (self.secondary_conversion_factor or 0.0)

    def _to_primary_qty_from_secondary(self, secondary_qty):
        """Convert secondary_qty -> primary_qty (in template's primary UoM) based on product config."""
        self.ensure_one()
        if not (self.is_secondary_uom and self.secondary_uom_id and self.uom_id):
            return 0.0

        if self.uom_id.category_id == self.secondary_uom_id.category_id:
            # Same category -> use Odoo engine
            return self.secondary_uom_id._compute_quantity(secondary_qty, self.uom_id)

        # Cross category -> divide by factor (guard zero)
        factor = self.secondary_conversion_factor or 0.0
        if float_is_zero(factor, precision_digits=6):
            return 0.0
        return secondary_qty / factor

    @api.depends('qty_available', 'virtual_available', 'secondary_uom_id', 'is_secondary_uom',
                 'uom_id', 'secondary_conversion_factor')
    def _compute_secondary_quantities(self):
        for product in self:
            if product.is_secondary_uom and product.secondary_uom_id and product.uom_id:
                # qty_available & virtual_available are in product.uom_id already
                product.qty_on_hand_secondary = product._to_secondary_qty(product.qty_available)
                product.qty_forecasted_secondary = product._to_secondary_qty(product.virtual_available)
            else:
                product.qty_on_hand_secondary = 0.0
                product.qty_forecasted_secondary = 0.0

    @api.depends('qty_on_hand_secondary', 'qty_forecasted_secondary',
                 'secondary_uom_name', 'secondary_uom_id', 'is_secondary_uom',
                 'secondary_cross_category', 'secondary_conversion_factor')
    def _compute_sec_labels(self):
        for rec in self:
            if rec.is_secondary_uom and rec.secondary_uom_id:
                rounding = rec.secondary_uom_id.rounding or 0.01
                onhand = float_round(rec.qty_on_hand_secondary or 0.0, precision_rounding=rounding)
                forecast = float_round(rec.qty_forecasted_secondary or 0.0, precision_rounding=rounding)
                u = rec.secondary_uom_name or ''
                # Optionally surface the factor when cross-category to aid users
                if rec.secondary_cross_category:
                    rec.qty_on_hand_secondary_label = f"{onhand:g} {u} On Hand (factor {rec.secondary_conversion_factor:g})"
                    rec.qty_forecasted_secondary_label = f"{forecast:g} {u} Forecasted (factor {rec.secondary_conversion_factor:g})"
                else:
                    rec.qty_on_hand_secondary_label = f"{onhand:g} {u} On Hand"
                    rec.qty_forecasted_secondary_label = f"{forecast:g} {u} Forecasted"
            else:
                rec.qty_on_hand_secondary_label = ""
                rec.qty_forecasted_secondary_label = ""

    # -------------------- CONSTRAINTS --------------------
    @api.constrains('is_secondary_uom', 'uom_id', 'secondary_uom_id', 'secondary_conversion_factor')
    def _check_secondary_uom_factor(self):
        for p in self:
            if not (p.is_secondary_uom and p.secondary_uom_id and p.uom_id):
                continue
            cross = p.secondary_uom_id.category_id != p.uom_id.category_id
            if cross:
                if p.secondary_conversion_factor is None or p.secondary_conversion_factor <= 0:
                    raise ValidationError(_(
                        "Product '%s': When Primary and Secondary UoMs are in different categories, "
                        "the 'Secondary per 1 Primary' factor must be a positive number."
                    ) % (p.display_name,))

    # -------------------- HEADER BUTTON ACTIONS --------------------
    def action_view_secondary_onhand(self):
        """Open the same quants view as the native 'On Hand' button."""
        self.ensure_one()
        open_quants = getattr(self, "action_open_quants", None)
        if callable(open_quants):
            return open_quants()
        action = self.env.ref('stock.product_open_quants').sudo().read()[0]
        action.setdefault('context', {})
        action['context'].update({
            'active_model': 'product.template',
            'active_id': self.id,
            'search_default_product_tmpl_id': self.id,
        })
        return action

    def action_view_secondary_forecasted(self):
        """Open the standard forecasted report for this product."""
        self.ensure_one()
        open_forecast = getattr(self, "action_open_forecast", None)
        if callable(open_forecast):
            return open_forecast()
        action = self.env.ref('stock.product_template_action_product_forecast_report', raise_if_not_found=False)
        if action:
            act = action.sudo().read()[0]
            act.setdefault('context', {})
            act['context'].update({
                'active_model': 'product.template',
                'active_id': self.id,
                'default_product_tmpl_id': self.id,
            })
            return act
        return False




# from odoo import api, fields, models
# from odoo.tools.float_utils import float_round
#
#
# class ProductTemplate(models.Model):
#     _inherit = 'product.template'
#
#     is_secondary_uom = fields.Boolean(
#         string="Is Secondary Unit?",
#         help="Enable to use a secondary unit of measure for this product.",
#     )
#     secondary_uom_id = fields.Many2one(
#         'uom.uom',
#         string="Secondary UOM",
#         help="Select the secondary unit of measure (same category as primary).",
#     )
#
#     # Helper for safe domain use in v17 views
#     secondary_uom_category_id = fields.Many2one(
#         'uom.category',
#         compute='_compute_sec_cat',
#         string="UoM Category (Helper)",
#     )
#
#     # Helper to print the unit name
#     secondary_uom_name = fields.Char(
#         string="Secondary UoM Name",
#         compute="_compute_secondary_uom_name",
#         store=False,
#     )
#
#     qty_on_hand_secondary = fields.Float(
#         string="On Hand (Secondary UOM)",
#         compute="_compute_secondary_quantities",
#         digits='Product Unit of Measure',
#     )
#     qty_forecasted_secondary = fields.Float(
#         string="Forecasted (Secondary UOM)",
#         compute="_compute_secondary_quantities",
#         digits='Product Unit of Measure',
#     )
#
#     # Labels for Option B (regular header buttons)
#     qty_on_hand_secondary_label = fields.Char(
#         compute="_compute_sec_labels", store=False)
#     qty_forecasted_secondary_label = fields.Char(
#         compute="_compute_sec_labels", store=False)
#
#     # --- computes ---
#     @api.depends('uom_id')
#     def _compute_sec_cat(self):
#         for rec in self:
#             rec.secondary_uom_category_id = rec.uom_id.category_id
#
#     @api.depends('secondary_uom_id')
#     def _compute_secondary_uom_name(self):
#         for rec in self:
#             rec.secondary_uom_name = rec.secondary_uom_id.name or ''
#
#     @api.depends('qty_available', 'virtual_available', 'secondary_uom_id', 'is_secondary_uom', 'uom_id')
#     def _compute_secondary_quantities(self):
#         for product in self:
#             if product.is_secondary_uom and product.secondary_uom_id:
#                 product.qty_on_hand_secondary = product.uom_id._compute_quantity(
#                     product.qty_available, product.secondary_uom_id
#                 )
#                 product.qty_forecasted_secondary = product.uom_id._compute_quantity(
#                     product.virtual_available, product.secondary_uom_id
#                 )
#             else:
#                 product.qty_on_hand_secondary = 0.0
#                 product.qty_forecasted_secondary = 0.0
#
#     @api.depends('qty_on_hand_secondary', 'qty_forecasted_secondary',
#                  'secondary_uom_name', 'secondary_uom_id', 'is_secondary_uom')
#     def _compute_sec_labels(self):
#         for rec in self:
#             if rec.is_secondary_uom and rec.secondary_uom_id:
#                 rounding = rec.secondary_uom_id.rounding or 0.01
#                 onhand = float_round(rec.qty_on_hand_secondary or 0.0, precision_rounding=rounding)
#                 forecast = float_round(rec.qty_forecasted_secondary or 0.0, precision_rounding=rounding)
#                 u = rec.secondary_uom_name or ''
#                 rec.qty_on_hand_secondary_label = f"{onhand:g} {u} On Hand"
#                 rec.qty_forecasted_secondary_label = f"{forecast:g} {u} Forecasted"
#             else:
#                 rec.qty_on_hand_secondary_label = ""
#                 rec.qty_forecasted_secondary_label = ""
#
#     # ---- header button actions (re-use native behavior) ----
#     def action_view_secondary_onhand(self):
#         """Open the same quants view as the native 'On Hand' button."""
#         self.ensure_one()
#         open_quants = getattr(self, "action_open_quants", None)
#         if callable(open_quants):
#             return open_quants()
#         action = self.env.ref('stock.product_open_quants').sudo().read()[0]
#         action.setdefault('context', {})
#         action['context'].update({
#             'active_model': 'product.template',
#             'active_id': self.id,
#             'search_default_product_tmpl_id': self.id,
#         })
#         return action
#
#     def action_view_secondary_forecasted(self):
#         """Open the standard forecasted report for this product."""
#         self.ensure_one()
#         open_forecast = getattr(self, "action_open_forecast", None)
#         if callable(open_forecast):
#             return open_forecast()
#         action = self.env.ref('stock.product_template_action_product_forecast_report', raise_if_not_found=False)
#         if action:
#             act = action.sudo().read()[0]
#             act.setdefault('context', {})
#             act['context'].update({
#                 'active_model': 'product.template',
#                 'active_id': self.id,
#                 'default_product_tmpl_id': self.id,
#             })
#             return act
#         return False
