# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

from collections import defaultdict
from odoo import fields, models
from odoo.tools import misc


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    print_format = fields.Selection(default='dymo')

    def _prepare_report_data(self):
        xml_id, data = super()._prepare_report_data()
        stock_lot = self.env['stock.lot']
        prod_exp_dates = []
        label_generated_from_picking = False
        if bool(data.get('custom_barcodes')):
            for key, value in data['custom_barcodes'].items():
                prod_custom_barcodes = value
                for barcodes in prod_custom_barcodes:
                    stock_lot_obj = stock_lot.search([('name', '=', barcodes[0])])
                    barcode_exp = []
                    if "expiration_date" in stock_lot_obj._fields:
                        exp_date = stock_lot_obj.expiration_date.strftime(misc.DEFAULT_SERVER_DATE_FORMAT) if stock_lot_obj.expiration_date else ""
                        prod_exp_dates.append((stock_lot_obj.name, exp_date))
                    # prod_exp_dates.append(barcode_exp)
        data.update({"prod_exp_dates": prod_exp_dates})
        # custom_barcodes_list = data['custom_barcodes'].items()
        if "move_line_ids" in self._fields:
            picking_data = []
            for move_line in self.move_line_ids:
                # if move_line.picking_id.picking_type_id.code == 'incoming' and move_line.picking_id not in picking_data:
                if not any(d['picking_name'] == move_line.picking_id.name for d in picking_data):
                    label_generated_from_picking = True
                    picking_data.append({
                        'picking_name': move_line.picking_id.name,
                        'picking_type': move_line.picking_id.picking_type_id.code,
                        'partner': move_line.picking_id.partner_id.display_name,
                        'date_done': move_line.picking_id.date_done.strftime(misc.DEFAULT_SERVER_DATE_FORMAT) if move_line.picking_id.date_done else ""
                    })
            data.update({"picking_data": picking_data[0] if picking_data else []})

        data.update({"is_picking": label_generated_from_picking})
        return xml_id, data
