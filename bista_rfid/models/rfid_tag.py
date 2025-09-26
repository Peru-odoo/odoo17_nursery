# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2021 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import fields, models, api


class RFIDTag(models.Model):
    _name = 'rfid.tag'
    _description = 'RFID Tags'

    @api.onchange('usage_type')
    def _picking_domain(self):
        for rec in self:
            if rec.usage_type == 'receipt':
                return {'domain': {'picking_id': [('picking_type_id.code', '=', 'incoming')]}}
            elif rec.usage_type == 'delivery':
                return {'domain': {'picking_id': [('picking_type_id.code', '=', 'outgoing')]}}
            else:
                return {'domain': {'picking_id': []}}

    name = fields.Char(string='RFID Tag', required=True)
    usage_type = fields.Selection([('receipt', 'Receipt'), ('delivery', 'Delivery'),
                                   ('product', 'Product'), ('stock_prod_lot', 'Lot/Serial No.'), ('n_a', 'N/A')],
                                  string="Usage Type", required=True)
    usage = fields.Reference(selection=[('stock.picking', 'Transfer'),
                                        ('product.product', 'Product'), ('stock.lot', 'Lot/Serial No.')],
                             string="Usage", compute='_get_usage', readonly=True)

    picking_id = fields.Many2one('stock.picking', string="Transfer", domain=_picking_domain)
    product_id = fields.Many2one('product.product', string="Product Variant")
    stock_prod_lot_id = fields.Many2one('stock.lot', string="Lot/Serial No.")
    assigned = fields.Boolean(string="Assigned?", compute="_compute_assigned")

    _sql_constraints = [
        ('rfid_tag_uniq_name', 'unique (name)', "Same RFID tag cannot be used for to multiple records."),
        ('rfid_tag_uniq_picking', 'unique (picking_id)', "Same Transfer cannot be have for to multiple RFID Tags."),
        ('rfid_tag_uniq_product', 'unique (product_id)', "Same Product cannot be have for to multiple RFID Tags."),
        ('rfid_tag_uniq_stock_prod_lot', 'unique (stock_prod_lot_id)',
         "Same Lot/Serial No. cannot be have for to multiple RFID Tags.")
    ]

    def _get_usage(self):
        for rec in self:
            if rec.usage_type in ['receipt', 'delivery'] and rec.picking_id:
                rec.usage = rec.picking_id
            elif rec.usage_type == 'product' and rec.product_id:
                rec.usage = rec.product_id
            elif rec.usage_type == 'stock_prod_lot' and rec.stock_prod_lot_id:
                rec.usage = rec.stock_prod_lot_id
            else:
                rec.usage = False

    def _compute_assigned(self):
        for rec in self:
            if rec.picking_id or rec.product_id or rec.stock_prod_lot_id:
                rec.assigned = True
            else:
                rec.assigned = False

    @api.onchange('usage_type')
    def _onchange_usage_type(self):
        if self.usage_type in ('receipt', 'delivery'):
            self.product_id = False
            self.stock_prod_lot_id = False
        elif self.usage_type == 'product':
            self.picking_id = False
            self.stock_prod_lot_id = False
        elif self.usage_type == 'stock_prod_lot':
            self.picking_id = False
            self.product_id = False
        else:
            self.picking_id = False
            self.product_id = False
            self.stock_prod_lot_id = False

    # @api.onchange('picking_id')
    # def _onchange_picking_id(self):
    #     for rec in self:
    #         if rec.picking_id:
    #             rec.picking_id.rfid_tag = rec.name
    #
    # @api.onchange('product_id')
    # def _onchange_product_id(self):
    #     for rec in self:
    #         if rec.product_id:
    #             rec.product_id.rfid_tag = rec.name
    #
    # @api.onchange('stock_prod_lot_id')
    # def _onchange_stock_prod_lot_id(self):
    #     for rec in self:
    #         if rec.stock_prod_lot_id:
    #             rec.stock_prod_lot_id.rfid_tag = rec.name

    # def write(self, vals):
    # @api.depends('usage_type')
    # def set_rfid_usage(self, vals):
    #     for rec in self:
    #         if rec.usage_type in ('receipt', 'delivery') and rec.picking_id:
    #             rec.picking_id.rfid_tag = rec.name
    #         if rec.usage_type == 'product' and rec.product_id:
    #             rec.product_id.rfid_tag = rec.name
    #         if rec.usage_type == 'stock_prod_lot' and rec.stock_prod_lot_id:
    #             rec.stock_prod_lot_id.rfid_tag = rec.name
        # res = super(RFIDTag, self).write(vals)
        # print(res)
        # return res

    def set_rfid_tag(self):
        # print("rfid_tag set_rfid_tag()", self.env.context)
        if self.env.context.get('skip_set_rfid_tag', False):
            return
        else:
            ctx = dict(self.env.context or {})
            ctx.update({'skip_set_rfid_tag_product': True})
            for rec in self:
                if rec.usage_type in ('receipt', 'delivery') and rec.picking_id:
                    # rec.picking_id.write({'rfid_tag': rec.name})
                    rec.picking_id.with_context(ctx).write({'rfid_tag': rec.id})
                if rec.usage_type == 'product' and rec.product_id:
                    # rec.product_id.write({'rfid_tag': rec.name})
                    rec.product_id.with_context(ctx).write({'rfid_tag': rec.id})
                if rec.usage_type == 'stock_prod_lot' and rec.stock_prod_lot_id:
                    # rec.stock_prod_lot_id.write({'rfid_tag': rec.name})
                    rec.stock_prod_lot_id.with_context(ctx).write({'rfid_tag': rec.id})

    @api.model
    def create(self, vals):
        res = super(RFIDTag, self).create(vals)
        res.set_rfid_tag()
        return res

    def write(self, values):
        vals_keys = values.keys()
        # NOTE: Setting the rfid_tag in current product/picking/lot as False
        #  before assigning the tag to new product/picking/lot
        # NOTE: values.get(<m2o_field>, False) == False, this check was added to remove the relationship
        #  on Product/Picking/Lot if we delete from RFID Tag view

        if 'picking_id' in vals_keys or values.get('picking_id', False) == False:
            self.picking_id.rfid_tag = False
        if 'product_id' in vals_keys or values.get('product_id', False) == False:
            self.product_id.rfid_tag = False
        if 'stock_prod_lot_id' in vals_keys or values.get('stock_prod_lot_id', False) == False:
            self.stock_prod_lot_id.rfid_tag = False

        res = super().write(values)
        self.set_rfid_tag()
        return res
