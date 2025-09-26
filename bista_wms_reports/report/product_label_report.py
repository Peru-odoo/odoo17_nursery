# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import models, api

# def _prepare_data(env, data):


class ReportProductTemplateLabelDymoInherit(models.AbstractModel):
    _inherit = 'report.product.report_producttemplatelabel_dymo'

    @api.model
    def _get_report_values(self, docids, data):
        res = super(ReportProductTemplateLabelDymoInherit, self)._get_report_values(docids, data)
        IrParamSudo = self.env['ir.config_parameter'].sudo()

        print_label_qr_code_settings = IrParamSudo.get_param('bista_wms_reports.use_qr_code_print_label')
        res.update({'print_label_qr_code_settings': print_label_qr_code_settings})

        return res
