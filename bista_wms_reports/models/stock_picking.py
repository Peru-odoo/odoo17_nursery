# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import fields, models, api


class PickingInh(models.Model):
    _inherit = 'stock.picking'

    def get_qr_picking_operations_settings(self):
        IrParamSudo = self.env['ir.config_parameter'].sudo()

        picking_operations_qr_code_settings = IrParamSudo.get_param('bista_wms_reports.use_qr_code_picking_operations')

        return picking_operations_qr_code_settings
    
    # for product package button
    def action_open_label_layout(self):
        action = self.env['ir.actions.act_window']._for_xml_id('product.action_open_label_layout')
        product_ids = []
        for lines in self.move_ids.move_line_ids:
            product_ids.append(lines.product_id.id)
        action['context'] = {'default_product_ids': product_ids}
        return action
    def action_bista_package(self):
        self.ensure_one()
        pass
        action = self.env['ir.actions.act_window']._for_xml_id('bista_wms_reports.action_open_bista_packages')
        wms_packaging_wizard = self.env['bista.wms.package']
        wms_packaging_wizard_id = wms_packaging_wizard.create({
            'result_package_ids': [(6, 0, self.move_line_ids.mapped('result_package_id').ids)]
        })
        action['res_id'] = wms_packaging_wizard_id.id
        return action