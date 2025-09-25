import json
import werkzeug.wrappers
from odoo import fields, models, api

import logging
import datetime

from odoo.tools import date_utils, DEFAULT_SERVER_DATETIME_FORMAT
# from odoo.http import JsonRequest, Response
from odoo.http import JsonRPCDispatcher, Response, request

_logger = logging.getLogger(__name__)


def default(o):
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    if isinstance(o, bytes):
        return str(o)


def valid_response(data, status=200):
    """Valid Response
    This will be return when the http request was successfully processed."""
    data = {
        "count": len(data) if not isinstance(data, str) else 1,
        "status": True,
        "data": data
    }
    return werkzeug.wrappers.Response(
        status=status, content_type="application/json; charset=utf-8", response=json.dumps(data, default=default),
    )


def invalid_response(typ, message=None, status=200):
    """Invalid Response

    This will be the return value whenever the server runs into an error
    either from the client or the server.

    :param str typ: type of error,
    :param str message: message that will be displayed to the user,
    :param int status: integer HTTP status code that will be sent in response body & header.
    """
    # return json.dumps({})
    response_status = False
    if eval(request.env.ref('bista_wms_api.http_status_code').sudo().value):
        status = status
        if typ == "not_found":
            response_status= True
    else:
        status = 200
    return werkzeug.wrappers.Response(
        status=status,
        content_type="application/json; charset=utf-8",
        response=json.dumps(
            {
                "code": status,
                "type": typ,
                "message": str(message) if str(message) else "wrong arguments (missing validation)",
                "status": response_status
            },
            default=datetime.datetime.isoformat,
        ),
    )


def extract_arguments(limit="80", offset=0, order="id", domain="", fields=[]):
    """Parse additional data  sent along request."""
    limit = int(limit)
    expresions = []
    if domain:
        expresions = [tuple(preg.replace(":", ",").split(",")) for preg in domain.split(",")]
        expresions = json.dumps(expresions)
        expresions = json.loads(expresions, parse_int=True)
    if fields:
        fields = fields.split(",")

    if offset:
        offset = int(offset)
    return [expresions, fields, offset, limit, order]


def _response(self, result=None, error=None):
    response = {'jsonrpc': '2.0', 'id': self.request_id}
    if error is not None:
        response['error'] = error
    if result is not None:
        # Start of customization
        if isinstance(result, werkzeug.wrappers.Response):
            return result
        try:
            rest_result = json.loads(result)
            if isinstance(rest_result, dict) and 'rest_api_flag' in rest_result and rest_result.get('rest_api_flag'):
                response.update(rest_result)
                response['result'] = None
            else:
                response['result'] = result
        except Exception as e:
            response['result'] = result
        # End of customization
        # response['result'] = result

    return self.request.make_json_response(response)


setattr(JsonRPCDispatcher, '_response', _response)  # overwrite the method


def convert_data_str(data):

    # Convert any data that is NOT [str, dictionary, array, tuple or bool] TO str
    if type(data) not in [str, dict, list, tuple, bool]:
        data = str(data)

    # Convert dictionary values that are NOT str TO str
    elif isinstance(data, dict):
        for key in data:
            if not isinstance(data[key], str) and not isinstance(data[key], list):
                data[key] = str(data[key])

            if isinstance(data[key], list):
                for index, elem in enumerate(data[key]):
                    if not isinstance(elem, str):
                        data[key][index] = str(elem)

    # Convert list elements that are NOT str TO str
    elif isinstance(data, list):
        for index, elem in enumerate(data):
            if not isinstance(elem, str):
                data[index] = str(elem)

    return data


def filter_by_last_sync_time(model_name, payload_data):
    """
    Filter based on last_sync_time(unix time stamp and date time format).
    """
    id_list = [] 
    if 'last_sync_timestamp' in payload_data and payload_data['last_sync_timestamp']:
        unix_timestamp = int(payload_data['last_sync_timestamp'])
        datetime_string = datetime.datetime.fromtimestamp(unix_timestamp).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
    elif 'last_sync_time' in payload_data and payload_data['last_sync_time']:
        datetime_string = payload_data['last_sync_time']
    domain = ['|', ("create_date", ">=", datetime_string),
                ("write_date", ">=", datetime_string)]

    if model_name == 'stock.picking.batch' or model_name == 'stock.picking':
        model_obj = request.env[model_name].sudo().search([])
        if model_name == 'stock.picking.batch':
            for val in model_obj:
                picking_ids = val.picking_ids.filtered(
                    lambda x: x.write_date >= datetime.datetime.strptime(datetime_string,
                                                            DEFAULT_SERVER_DATETIME_FORMAT) or x.create_date >= datetime.datetime.strptime(
                        datetime_string, DEFAULT_SERVER_DATETIME_FORMAT))
                if picking_ids and val.id not in id_list:
                    id_list.append(val.id)

        for val in model_obj:
            move_ids = val.move_ids.filtered(
                lambda x: x.write_date >= datetime.datetime.strptime(datetime_string,
                                                            DEFAULT_SERVER_DATETIME_FORMAT) or x.create_date >= datetime.datetime.strptime(
                    datetime_string, DEFAULT_SERVER_DATETIME_FORMAT))
            if move_ids and val.id not in id_list:
                id_list.append(val.id)

        for val in model_obj:
            move_line_ids = val.move_line_ids.filtered(
                lambda x: x.write_date >= datetime.datetime.strptime(datetime_string,
                                                            DEFAULT_SERVER_DATETIME_FORMAT) or x.create_date >= datetime.datetime.strptime(
                    datetime_string, DEFAULT_SERVER_DATETIME_FORMAT))
            if move_line_ids and val.id not in id_list:
                id_list.append(val.id)

    if id_list:
        domain += [('id', 'in', id_list)]

    return domain
  
# def filter_by_last_sync_time(model_name, payload_data):
#     """
#     Filter based on last_sync_time.
#     """
#     id_list = []
#     domain = ['|', ("create_date", ">=", payload_data['last_sync_time']),
#               ("write_date", ">=", payload_data['last_sync_time'])]

#     if model_name == 'stock.picking.batch' or model_name == 'stock.picking':
#         model_obj = request.env[model_name].sudo().search([])
#         if model_name == 'stock.picking.batch':
#             for val in model_obj:
#                 picking_ids = val.picking_ids.filtered(
#                     lambda x: x.write_date >= datetime.strptime(payload_data['last_sync_time'],
#                                                                 '%Y-%m-%dT%H:%M:%S.%f') or x.create_date >= datetime.strptime(
#                         payload_data['last_sync_time'], '%Y-%m-%dT%H:%M:%S.%f'))
#                 if picking_ids and val.id not in id_list:
#                     id_list.append(val.id)

#         for val in model_obj:
#             move_ids = val.move_ids.filtered(
#                 lambda x: x.write_date >= datetime.strptime(payload_data['last_sync_time'],
#                                                             '%Y-%m-%dT%H:%M:%S.%f') or x.create_date >= datetime.strptime(
#                     payload_data['last_sync_time'], '%Y-%m-%dT%H:%M:%S.%f'))
#             if move_ids and val.id not in id_list:
#                 id_list.append(val.id)

#         for val in model_obj:
#             move_line_ids = val.move_line_ids.filtered(
#                 lambda x: x.write_date >= datetime.strptime(payload_data['last_sync_time'],
#                                                             '%Y-%m-%dT%H:%M:%S.%f') or x.create_date >= datetime.strptime(
#                     payload_data['last_sync_time'], '%Y-%m-%dT%H:%M:%S.%f'))
#             if move_line_ids and val.id not in id_list:
#                 id_list.append(val.id)

#     if id_list:
#         domain += [('id', 'in', id_list)]

#     return domain


def prepare_config_settings(self, record_id, to_do):
    IrConfigParameter = self.env['ir.config_parameter'].sudo()
    user_id = self.env.user
    IrModule = self.env['ir.module.module']
    try:
        batch_transfer = IrModule.search([('name', '=', 'stock_picking_batch')])
        delivery_method = IrModule.search([('name', '=', 'delivery')])
        stock_barcode = IrModule.search([('name', '=', 'stock_barcode')])
        quality = IrModule.search([('name', '=', 'quality_control')])
        product_expiry = IrModule.search([('name', '=', 'product_expiry')])
        settings_vals = {
            'user_id': user_id.id,
            'warehouse_id': record_id.id if record_id._name == 'stock.warehouse' else record_id.warehouse_id.id,
            'company_id': record_id.company_id.id,
            'product_packages': user_id.has_group('stock.group_tracking_lot'),
            'product_packaging': user_id.has_group('product.group_stock_packaging'),
            'wms_licensing_key': IrConfigParameter.get_param('bista_wms_api.wms_licensing_key') or "",
            'batch_transfer': True if batch_transfer and batch_transfer.state == 'installed' else False,
            'quality': True if quality and quality.state == 'installed' else False,
            'barcode_scanner': True if stock_barcode and stock_barcode.state == 'installed' else False,
            'barcode_gst1': user_id.has_group('stock.group_stock_lot_print_gs1'),
            'delivery_method': True if delivery_method and delivery_method.state == 'installed' else False,
            'lot_on_invoice': user_id.has_group('stock_account.group_lot_on_invoice'),
            'consignment': user_id.has_group('stock.group_tracking_owner'),
            'product_variants': user_id.has_group('product.group_product_variant'),
            'units_of_measure': user_id.has_group('uom.group_uom'),
            'storage_locations': user_id.has_group('stock.group_stock_multi_locations'),
            'multi_step_routes': user_id.has_group('stock.group_adv_location'),
            'storage_categories': user_id.has_group('stock.group_stock_storage_categories'),
            'expiration_dates': True if product_expiry and product_expiry.state == 'installed' else False,
            'use_qr_code': IrConfigParameter.get_param('bista_wms_reports.use_qr_code'),
            'use_qr_code_print_label': IrConfigParameter.get_param('bista_wms_reports.use_qr_code_print_label'),
            'use_qr_code_picking_operations': IrConfigParameter.get_param(
                'bista_wms_reports.use_qr_code_picking_operations'),
            'use_qr_code_batch_operations': IrConfigParameter.get_param(
                'bista_wms_reports.use_qr_code_batch_operations'),
        }
        if to_do == 'create':
            self.env['bista.wms.config.settings'].create(settings_vals)
        elif to_do == 'update':
            record_id.write(settings_vals)
    except Exception as e:
        _logger.exception("Error while creating or updating bista wms config settings: %s", e)

def app_changed_create_write(stock_picking_obj, line_obj, new_vals, prev_move_line_obj=None):
    if prev_move_line_obj:
        html = ""
        move_line_obj = line_obj
        for item in new_vals:
            model, field = 'stock.move.line', item
            if isinstance(request.env[model]._fields[field], (fields.Many2one)):
                model_id = request.env['ir.model'].sudo().search([('model', '=', model)]) # 480
                related_model_name = request.env['ir.model.fields'].sudo().search([('ttype', '=', 'many2one'), ('model_id', '=', model_id.id), ('name', '=', item)], limit=1).relation
                changed_m2o_f_name = request.env[related_model_name].sudo().search([('id', '=', new_vals[item])]).name
                if str(getattr(move_line_obj, item).name) != str(changed_m2o_f_name):
                    html += "<p style='margin: 0 !important;'>" + request.env['stock.move.line']._fields[item].string + ": " + str(getattr(move_line_obj, item).name) + "&rarr;" \
                                                                                                                                + str(changed_m2o_f_name) + "</p>" + "</br>"
            else:
                if new_vals[item] != getattr(move_line_obj, item):
                    html += "<p style='margin: 0 !important;'>" + request.env['stock.move.line']._fields[item].string + ": " + str(getattr(move_line_obj, item)) + "&rarr;" \
                                                                                                                            + str(new_vals[item]) + "</p>" + "</br>"
        if html:
            obj = request.env['bista.app.change'].sudo().create({
                                                'res_model': move_line_obj._name,
                                                'app_created': False,
                                                'app_changes': html,
                                    })
            obj.app_changed_id = move_line_obj
            # stock_picking_obj.app_change_ids = [(4, obj.id)]
            return obj
    else:
        html = ""
        for item in new_vals:
            model, field = 'stock.move.line', item
            if isinstance(request.env[model]._fields[field], (fields.Many2one)):
                html += "<p style='margin: 0 !important;'>" + request.env['stock.move.line']._fields[item].string + ": " + str(getattr(line_obj, item).name) + "</p>" + "</br>"
            else:
                html += "<p style='margin: 0 !important;'>" + request.env['stock.move.line']._fields[item].string + ": " + str(getattr(line_obj, item)) + "</p>" + "</br>"
        if html:
            obj = request.env['bista.app.change'].sudo().create({
                                                'res_model': line_obj._name,
                                                'app_created': True,
                                                'app_changes': html,
                                    })
            obj.app_changed_id = line_obj
            stock_picking_obj.app_change_ids = [(4, obj.id)]
