# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import models, api


class BistaProductLabelReportLotLabelDymo(models.AbstractModel):
    _name = 'report.stock.report_lot_label'
    _description = 'Lot Label Report Dymo'

    @api.model
    def _get_report_values(self, docids, data=None):
        all_docids = data.get('all_docids', []) if data.get('all_docids', False) else docids
        return {
            'docids': all_docids,
            'data': data,
            'docs': self.env['stock.lot'].browse(all_docids),
        }
    
    # def _get_report_values(self, docids, data=None):
    #     return {
    #         'docids': data['all_docids'],
    #         'data': data,
    #         'docs': self.env['stock.lot'].browse(data['all_docids']),
    #     }
