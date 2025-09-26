# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    use_qr_code = fields.Boolean(string="Use QR Codes?", default=False)
    use_qr_code_print_label = fields.Boolean(string="In Product Label", default=False,
                                             help="Enabling use QR Code in Product Label PDF instead of Barcode")
    use_qr_code_picking_operations = fields.Boolean(string="In Picking Operations", default=False,
                                                    help="Enabling the use of QR Code in Picking Operations PDF instead of Barcode")
    use_qr_code_batch_operations = fields.Boolean(string="In Batch/Wave Operations", default=False,
                                                    help="Enabling the use of QR Code in Batch/Wave Transfer Operations PDF instead of Barcode")

    @api.model
    def set_values(self):
        """qr code setting field values"""
        res = super(ResConfigSettings, self).set_values()
        set_param = self.env['ir.config_parameter'].set_param
        set_param('bista_wms_reports.use_qr_code_print_label', self.use_qr_code_print_label)
        set_param('bista_wms_reports.use_qr_code_picking_operations', self.use_qr_code_picking_operations)
        set_param('bista_wms_reports.use_qr_code_batch_operations', self.use_qr_code_batch_operations)
        return res

    @api.model
    def get_values(self):
        """qr code limit getting field values"""
        res = super(ResConfigSettings, self).get_values()
        use_qr_code_print_label_value = self.env['ir.config_parameter'].sudo().get_param(
            'bista_wms_reports.use_qr_code_print_label')
        use_qr_code_picking_operations_value = self.env['ir.config_parameter'].sudo().get_param(
            'bista_wms_reports.use_qr_code_picking_operations')
        use_qr_code_batch_operations_value = self.env['ir.config_parameter'].sudo().get_param(
            'bista_wms_reports.use_qr_code_batch_operations')
        res.update(
            use_qr_code_print_label=use_qr_code_print_label_value,
            use_qr_code_picking_operations=use_qr_code_picking_operations_value,
            use_qr_code_batch_operations=use_qr_code_batch_operations_value
        )
        return res
