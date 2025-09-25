# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.addons.bista_wms_api.common import prepare_config_settings
import ast


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    wms_licensing_key = fields.Char(string="WMS Licensing Key", default=False)
    user_check_restriction = fields.Boolean(string='User Restriction', default=True)
    enable_search_limit = fields.Boolean(string="Enable Search Limit", config_parameter='bista_wms_api.enable_search_limit')
    def_search_limit = fields.Integer(string="Search Limit", config_parameter='bista_wms_api.def_search_limit')
    restrict_stock_quants_in_location = fields.Boolean(string="Restrict Stock Quants in Location", config_parameter='bista_wms_api.restrict_stock_quants_in_location')

    @api.model
    def set_values(self):
        """qr code setting field values"""
        res = super(ResConfigSettings, self).set_values()
        set_param = self.env['ir.config_parameter'].set_param
        set_param('bista_wms_api.wms_licensing_key', self.wms_licensing_key)
        set_param('bista_wms_api.user_check_restriction', self.user_check_restriction)
        set_param('bista_wms_api.restrict_stock_quants_in_location', self.restrict_stock_quants_in_location)
        return res

    @api.model
    def get_values(self):
        """qr code limit getting field values"""
        res = super(ResConfigSettings, self).get_values()
        wms_licensing_key_value = self.env['ir.config_parameter'].sudo().get_param('bista_wms_api.wms_licensing_key')
        user_check_restriction_value = self.env['ir.config_parameter'].sudo().get_param('bista_wms_api.user_check_restriction')
        restrict_stock_quants_in_location_value = ast.literal_eval(self.env['ir.config_parameter'].sudo().get_param('bista_wms_api.restrict_stock_quants_in_location', 'False'))
        res.update(
            wms_licensing_key=wms_licensing_key_value,
            user_check_restriction=user_check_restriction_value,
            restrict_stock_quants_in_location=restrict_stock_quants_in_location_value,
        )
        return res

    def execute(self):
        ConfigSettings = super(ResConfigSettings, self).execute()
        StockWarehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)])
        for warehouse_id in StockWarehouse:
            WmsConfig_obj = self.env['bista.wms.config.settings'].search(
                [('company_id', '=', self.env.company.id), ('warehouse_id', '=', warehouse_id.id)])
            if WmsConfig_obj:
                # for record in WmsConfig_obj:
                prepare_config_settings(self, WmsConfig_obj,'update')
            else:
                prepare_config_settings(self, warehouse_id, 'create')
        
        stock_picking_user_rule = self.env.ref('bista_wms_api.stock_picking_user_rule')
        stock_picking_batch_user_rule = self.env.ref('bista_wms_api.stock_picking_batch_user_rule')

        if self.user_check_restriction:
            if stock_picking_user_rule:
                stock_picking_user_rule.write({'active': True})
            if stock_picking_batch_user_rule:
                stock_picking_batch_user_rule.write({'active': True})
        else:
            if stock_picking_user_rule:
                stock_picking_user_rule.write({'active': False})
            if stock_picking_batch_user_rule:
                stock_picking_batch_user_rule.write({'active': False})

        return ConfigSettings
