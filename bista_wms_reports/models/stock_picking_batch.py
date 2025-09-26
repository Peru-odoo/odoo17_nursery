# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import fields, models, api


class ModelName(models.Model):
    _inherit = "stock.picking.batch"

    def get_qr_batch_operations_settings(self):
        IrParamSudo = self.env['ir.config_parameter'].sudo()

        batch_operations_qr_code_settings = IrParamSudo.get_param('bista_wms_reports.use_qr_code_batch_operations')

        return batch_operations_qr_code_settings
