# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

from collections import defaultdict
from odoo import fields, models


class LotLabelLayout(models.TransientModel):
    _inherit = 'lot.label.layout'

    def process(self):
        self.ensure_one()
        all_docids = []
        xml_id = 'stock.action_report_lot_label'
        if self.print_format == 'zpl':
            xml_id = 'stock.label_lot_template'
        if self.label_quantity == 'lots':
            docids = self.move_line_ids.lot_id.ids
            all_docids = docids
        else:
            uom_categ_unit = self.env.ref('uom.product_uom_categ_unit')
            quantity_by_lot = defaultdict(int)
            for move_line in self.picking_ids.move_line_ids:
                if not move_line.lot_id:
                    continue
                if move_line.product_uom_id.category_id == uom_categ_unit:
                    quantity_by_lot[move_line.lot_id.id] += int(move_line.qty_done)
                else:
                    quantity_by_lot[move_line.lot_id.id] += 1
            docids = []
            for lot_id, qty in quantity_by_lot.items():
                docids.append([lot_id] * qty)
            for val in docids:
                all_docids += val 
        report_action = self.env.ref(xml_id).report_action(self, data={'all_docids': all_docids})
        report_action.update({'close_on_report_download': True})
        return report_action


