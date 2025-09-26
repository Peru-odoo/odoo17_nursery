# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2021 (http://www.bistasolutions.com)
#
##############################################################################

import logging
from odoo import api, fields, models, _
from odoo.modules.module import get_module_resource
from odoo.exceptions import UserError
import xlrd
import base64

_logger = logging.getLogger(__name__)


class RFIDTagImport(models.TransientModel):
    _name = 'rfid.tag.import'
    _description = "RFID Tag Import"

    file_for_import = fields.Binary(string='File')

    def action_import_rfid_data(self):
        rfid_tags = self.env['rfid.tag'].search([])
        existing_rfid_tags = rfid_tags.mapped('name')
        duplicate_tags = []

        for wizard in self:
            rfid_tag_obj = self.env['rfid.tag']
            rfid_tag_obj_usage_type_dict = dict(rfid_tag_obj._fields['usage_type'].selection)
            try:
                wb = xlrd.open_workbook(file_contents=base64.decodebytes(self.file_for_import))
                for sheet in wb.sheets():
                    for row in range(1, sheet.nrows):
                        if sheet.cell(row, 0).value in existing_rfid_tags:
                            rfid_tag_rec = rfid_tags.search([('name', '=', sheet.cell(row, 0).value)])
                            # duplicate_tag_msg = (rfid_tag_rec.name + " - " + rfid_tag_rec.usage.name_get()[0][1]) if rfid_tag_rec.usage else rfid_tag_rec.name
                            duplicate_tag_msg = (rfid_tag_rec.name + " - " + rfid_tag_rec.usage.display_name) if rfid_tag_rec.usage else rfid_tag_rec.name
                            duplicate_tags.append(duplicate_tag_msg)
                            # duplicate_tags.append(sheet.cell(row, 0).value)
                        else:
                            # for col in range(sheet.ncols):
                            #     print(sheet.cell(row, col).value)
                            rfid_tag_val = ""
                            usage_type_val = ""
                            picking_id_val = False
                            product_id_val = False
                            stock_prod_lot_id_val = False
                            assigned_val = False

                            rfid_tag = sheet.cell(row, 0).value,
                            usage_type = sheet.cell(row, 1).value
                            picking_id = sheet.cell(row, 2).value
                            product_id = sheet.cell(row, 3).value
                            stock_prod_lot_id = sheet.cell(row, 4).value

                            rfid_tag_val = rfid_tag[0]

                            if usage_type in ('Receipt', 'Delivery', 'Product', 'Lot/Serial No.'):
                                usage_type_arr = [
                                    key for key, value in rfid_tag_obj_usage_type_dict.items() if value == usage_type
                                ]
                                usage_type_val = usage_type_arr[0]
                            else:
                                usage_type_val = 'n_a'

                            if picking_id != "" and picking_id:
                                stock_picking_obj = self.env['stock.picking'].search([('name', '=', picking_id)], limit=1)
                                picking_id_val = stock_picking_obj.id if stock_picking_obj else False
                                # assigned_val = True
                            if product_id != "" and product_id:
                                product_product_obj = self.env['product.product'].name_search(product_id)
                                product_id_val = product_product_obj[0][0] if product_product_obj else False
                                # assigned_val = True
                            if stock_prod_lot_id != "" and stock_prod_lot_id:
                                stock_prod_lot_obj = self.env['stock.lot'].search(
                                    [('name', '=', stock_prod_lot_id)], limit=1)
                                stock_prod_lot_id_val = stock_prod_lot_obj.id if stock_prod_lot_obj else False
                                # assigned_val = True

                            rfid_tag_obj.create({
                                'name': rfid_tag_val,
                                'usage_type': usage_type_val,
                                'picking_id': picking_id_val,
                                'product_id': product_id_val,
                                'stock_prod_lot_id': stock_prod_lot_id_val,
                            })
            except xlrd.biffh.XLRDError:
                raise UserError('Only excel files are supported.')
            except Exception as e:
                raise UserError('No such file or directory found. \n%s.' % e.args)

        _logger.warning(f"Duplicate RFID Tags found during import: {duplicate_tags}")
        if duplicate_tags:
            duplicate_tags_str = "\n".join(duplicate_tags)
            message_id = self.env['message.wizard'].sudo().create({
                'message_one': _(f'Following RFID Tags are not imported because they already exists in the system.'),
                'message_two': _(duplicate_tags_str)
            })
            return {
                'type': 'ir.actions.act_window',
                'name': 'Duplicate RFID Tags',
                'res_model': 'message.wizard',
                'view_mode': 'form',
                'target': 'new',
                'res_id': message_id.id
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
    
    def download_template_file(self):
        xlsx_file_path = get_module_resource('bista_rfid', 'static/src', 'RFID_tag_template.xlsx')
        if xlsx_file_path:
            return {
                'type': 'ir.actions.act_url',
                'url': '/bista_rfid/static/src/RFID_tag_template.xlsx',
                'target': 'new',
            }
        else:
            raise UserError(_('No Template Found'))
