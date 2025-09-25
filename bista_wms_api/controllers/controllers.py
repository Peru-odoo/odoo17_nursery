# -*- coding: utf-8 -*-
import json
import logging
import functools
from collections import defaultdict
from odoo.exceptions import UserError
from odoo import _

from odoo import http
from odoo.exceptions import AccessDenied, AccessError
from odoo.http import request, content_disposition, serialize_exception as _serialize_exception
from odoo.addons.bista_wms_api.common import invalid_response, valid_response, convert_data_str, filter_by_last_sync_time, app_changed_create_write
from odoo.tools.safe_eval import safe_eval, time
from odoo.tools import html_escape
from odoo.addons.web.controllers.report import ReportController
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

import werkzeug.wrappers
from werkzeug.urls import url_encode, url_decode, iri_to_uri

import werkzeug.wrappers
import ast

_logger = logging.getLogger(__name__)



def validate_token(func):
    """."""

    @functools.wraps(func)
    def wrap(self, *args, **kwargs):
        """."""
        access_token = request.httprequest.headers.get("access_token")
        if not access_token:
            return invalid_response("access_token_not_found", "missing access token in request header", 200)
        access_token_data = (
            request.env["api.access_token"].sudo().search([("token", "=", access_token)], order="id DESC", limit=1)
        )

        if access_token_data.find_one_or_create_token(user_id=access_token_data.user_id.id) != access_token:
            return invalid_response("access_token", "token seems to have expired or invalid", 401)

        request.session.update(user=access_token_data.user_id.id)
        request.update_env(user=access_token_data.user_id.id)
        return func(self, *args, **kwargs)

    return wrap


class BistaWmsApi(http.Controller):
    """Warehouse Management System Controller"""

    @staticmethod
    def _get_user_stock_group(self):
        access_token = request.httprequest.headers.get("access-token")
        if access_token:
            user_id = request.env['api.access_token'].sudo().search([('token', '=', access_token)], limit=1).user_id
            is_admin = 0
            if user_id.has_group('stock.group_stock_manager'):
                is_admin = 1
            res_config_settings = request.env['res.config.settings'].sudo().search([], order='id desc', limit=1)

            if not res_config_settings.user_check_restriction:
                if is_admin == 0:
                    is_admin = 1
                return user_id, is_admin
            return user_id, is_admin
        return False

    @staticmethod
    def auth_login_response_data(data):

        response_data = {
            **{
                "status": True,
                "count": len(data) if not isinstance(data, str) else 1,
            },
            **data
        }

        return response_data

    @http.route("/api/auth/login", methods=["GET", "POST"], type="json", auth="none", csrf=False)
    def auth_login(self, **post):
        """The token URL to be used for getting the access_token.

        str post[db]: db of the system, in which the user logs in to.

        str post[login]: username of the user

        str post[password]: password of the user

        :param list[str] str post: **post must contain db, login and password.
        :returns: https response
            if failed error message in the body in json format and
            if successful user's details with the access_token.
        """
        _token = request.env["api.access_token"]
        params = ["db", "login", "password"]
        req_data = json.loads(request.httprequest.data.decode())  # convert the bytes format to dict format
        req_params = {key: req_data.get(key) for key in params if req_data.get(key)}
        db, username, password = (
            req_params.get("db"),
            req_params.get("login"),
            req_params.get("password"),
        )
        _credentials_includes_in_body = all([db, username, password])
        if not _credentials_includes_in_body:
            # The request post body is empty the credentials maybe passed via the headers.
            headers = request.httprequest.headers
            db = headers.get("db")
            username = headers.get("login")
            password = headers.get("password")
            _credentials_includes_in_headers = all([db, username, password])
            if not _credentials_includes_in_headers:
                # Empty 'db' or 'username' or 'password:
                return invalid_response(
                    "missing error", "Either of the following are missing [db, username,password]", 200,
                )
        # Login in odoo database:
        session_info = []
        try:
            request.session.authenticate(db, {'login': username, 'password': password, 'type': 'password'})
            session_info = request.env['ir.http'].session_info().get('server_version_info', [])
        except AccessError as aee:
            return invalid_response("Access error", "Error: %s" % aee.name)
        except AccessDenied as ade:
            return invalid_response("Access denied", "Login, password or db invalid")
        except Exception as e:
            # Invalid database:
            info = "The database name is not valid {}".format(e)
            error = "invalid_database"
            _logger.error(info)
            return invalid_response(typ=error, message=info, status=200)

        uid = request.session.uid
        # odoo login failed:
        if not uid:
            info = "authentication failed"
            error = "authentication failed"
            _logger.error(info)
            return invalid_response(status=200, typ=error, message=info)

        # Generate tokens
        access_token = _token.find_one_or_create_token(user_id=uid, create=True)
        warehouse_id = request.env.user.warehouse_id
        product_packaging = request.env.user.has_group('product.group_stock_packaging')
        product_packages = request.env.user.has_group('stock.group_tracking_lot')
        allowed_companies_data = []
        for company_id in request.env.user.company_ids:
            allowed_companies_data.append({
                'id':company_id.id,
                'name':str(company_id.name)
            })

        data = {
            "uid": uid,
            "user_context": convert_data_str(dict(request.env.context)) if uid else {},
            "company_id": request.env.user.company_id.id if uid else None,
            "company_ids": convert_data_str(request.env.user.company_ids.ids[::-1]) if uid else None,
            "allowed_companies": allowed_companies_data,
            "partner_id": request.env.user.partner_id.id,
            "warehouse_id": [str(warehouse_id.id),
                             warehouse_id.name] if warehouse_id else [],
            'procurement_steps': {"delivery_steps": str(warehouse_id.reception_steps or ""),
                                  "reception_steps": str(warehouse_id.delivery_steps or "")},
            "product_packages": product_packages,
            "product_packaging": product_packaging,
            "access_token": access_token,
            "company_name": request.env.user.company_name or "",
            # "currency": request.env.user.currency_id.name,
            "country": request.env.user.country_id.name or "",
            "contact_address": request.env.user.contact_address or "",
            # "customer_rank": request.env.user.customer_rank,
            "session_info": session_info,
            "wms_licensing_key": request.env['ir.config_parameter'].sudo().get_param(
                'bista_wms_api.wms_licensing_key') or "",
        }

        response_data = self.auth_login_response_data(data)

        # response_data = {
        #     **{
        #         "status": True,
        #         "count": len(data) if not isinstance(data, str) else 1,
        #     },
        #     **data
        # }

        return werkzeug.wrappers.Response(
            status=200,
            content_type="application/json; charset=utf-8",
            headers=[("Cache-Control", "no-store"), ("Pragma", "no-cache")],
            response=json.dumps(response_data)
        )

    @validate_token
    @http.route("/api/get_product_list", type="http", auth="none", methods=["GET"], csrf=False)
    def get_product_list(self, **payload):
        """ NOTE: DEPRECATED API for now, Gets the specific time frame from request and returns product details."""

        product_template_obj = request.env['product.template']

        payload_data = payload

        product_list_data = []
        response_data = {'rest_api_flag': True}

        domain = []

        if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
            domain += filter_by_last_sync_time('product.template', payload_data)

        if 'create_date' in payload_data and payload_data['create_date']:
            domain.append(('create_date', '>=', payload_data['create_date']))

        if 'write_date' in payload_data and payload_data['write_date']:
            domain.append(('write_date', '>=', payload_data['write_date']))

        products = product_template_obj.sudo().search(domain, order="id ASC")

        if products:
            for product in products:
                product_list_data.append({
                    'id': product.id,
                    'name': product.name,
                    'list_price': product.list_price,
                    'uom_id': [str(product.uom_id.id), product.uom_id.name] if product.uom_id else [],
                    'create_uid': [str(product.create_uid.id), product.create_uid.name] if product.create_uid else [],
                    'create_date': product.create_date,
                    'write_uid': [str(product.write_uid.id), product.write_uid.name] if product.write_uid else [],
                    'write_date': product.write_date,
                })
            response_data.update({'data': product_list_data})

            if response_data:
                # return valid_response(response_data)
                return valid_response(product_list_data)
            else:
                return invalid_response('not_found', 'Product data not found.')
        else:
            return invalid_response('not_found', 'No product record found.')

    def _prepare_inventory_warehouse_domain(self, domain):
        return domain

    @staticmethod
    def _get_picking_fields(self):
        stock_picking_type_obj = request.env['stock.picking.type'].search([])
        user_id, is_admin = self._get_user_stock_group(self)
        res = []
        picking_type_color_code = ['a2a2a2','ee2d2d','dc8534','e8bb1d','5794dd','9f628f','db8865',
                                                '41a9a2', '304be0', 'ee2f8a', '61c36e', '9872e6']
        
        # domains = {
        #     # 'count_picking_draft': [('state', '=', 'draft')],
        #     # 'count_picking_waiting': [('state', 'in', ('confirmed', 'waiting'))],
        #     'count_picking_ready': [('state', '=', 'assigned')],
        #     # 'count_picking': [('state', 'in', ('assigned', 'waiting', 'confirmed'))],
        #     # 'count_picking_late': [('scheduled_date', '<', time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)),
        #     #                        ('state', 'in', ('assigned', 'waiting', 'confirmed'))],
        #     # 'count_picking_backorders': [('backorder_id', '!=', False),
        #     #                              ('state', 'in', ('confirmed', 'assigned', 'waiting'))],
        # }
        # for field in domains:
        #     data = request.env['stock.picking'].read_group(domains[field] + [
        #         ('company_id', '=', request.env.user.company_id.id),
        #         ('state', 'not in', ('done', 'cancel')),
        #         ('picking_type_id', 'in', stock_picking_type_obj.ids)
        #     ], ['picking_type_id'], ['picking_type_id'])
        #     count = {
        #         # stock_picking_type_obj.browse(x['picking_type_id'][0]).name.lower().replace(" ", "_"): x['picking_type_id_count']
        #         x['picking_type_id'][0]: x['picking_type_id_count'] for x in data if x['picking_type_id']
        #     }
        #     # res.append(count)
        #     for record in stock_picking_type_obj.search([('company_id', '=', request.env.user.company_id.id)],
        #                                                 order='sequence'):
        #         # record[field] = count.get(record.id, 0)
        #         res.append({
        #             "id": record.id,
        #             "name": record.name,
        #             "code": record.code,
        #             "qty": count.get(record.id, 0),
        #             "sequence": record.sequence,
        #             # record.name.lower().replace(" ", "_"): count.get(record.id, 0)
        #         })

        # NOTE: New code for returning Ready, Waiting & Late pickings.
        if is_admin == 0:
            #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
            # for record in stock_picking_type_obj.search([('company_id', '=', request.env.user.company_id.id),
            #                                              ('warehouse_id', '=', user_id.warehouse_id.id)],
            #                                             order='sequence'):
            domain = []
            domain += self._prepare_inventory_warehouse_domain([('warehouse_id', '=', user_id.warehouse_id.id)])
            for record in stock_picking_type_obj.with_context(user_id_filtering=True).search(domain, order='sequence'):
                res.append({
                    "id": record.id,
                    "name": record.name,
                    "code": record.code,
                    "sequence": record.sequence,
                    "count_picking_draft": record.count_picking_draft,
                    "count_picking_waiting": record.count_picking_waiting,
                    "count_picking_ready": record.count_picking_ready,
                    "count_picking_late": record.count_picking_late,
                    "count_picking": record.count_picking,
                    "count_picking_backorders": record.count_picking_backorders,
                    "color": record.color,
                    "picking_type_color_code": picking_type_color_code,
                    "warehouse_id": [str(record.warehouse_id.id),
                                     record.warehouse_id.name] if record.warehouse_id else []
                })
        else:
            #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
            # for record in stock_picking_type_obj.search([('company_id', '=', request.env.user.company_id.id)],
            #                                             order='sequence'):
            for record in stock_picking_type_obj.search([],order='sequence'):
                res.append({
                    "id": record.id,
                    "name": record.name,
                    "code": record.code,
                    "sequence": record.sequence,
                    "count_picking_draft": record.count_picking_draft,
                    "count_picking_waiting": record.count_picking_waiting,
                    "count_picking_ready": record.count_picking_ready,
                    "count_picking_late": record.count_picking_late,
                    "count_picking": record.count_picking,
                    "count_picking_backorders": record.count_picking_backorders,
                    "color": record.color,
                    "picking_type_color_code": picking_type_color_code,
                    "warehouse_id": [str(record.warehouse_id.id),
                                     record.warehouse_id.name] if record.warehouse_id else []
                })
        # batch_transfer = request.env['ir.module.module'].search([('name', '=', 'stock_picking_batch')])
        # is_batch_transfer = True if batch_transfer and batch_transfer.state == 'installed' else False,

        stock_picking_batch_obj = request.env['stock.picking.batch']
        #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
        # batch_picking_count = stock_picking_batch_obj.search_count(
        #     [('state', '=', 'in_progress'), ('company_id', '=', request.env.user.company_id.id),
        #      ('is_wave', '=', False)]) 
        batch_picking_count = stock_picking_batch_obj.search_count(
            [('state', '=', 'in_progress'),('is_wave', '=', False)])
        # if is_batch_transfer else 0
        res.append({
            "id": 0,
            "name": "Batch Transfers",
            "code": "",
            "sequence": 0,
            "count_picking_draft": 0,
            "count_picking_waiting": 0,
            "count_picking_ready": batch_picking_count,
            "count_picking_late": 0,
            "count_picking": 0,
            "count_picking_backorders": 0,
        })

        wave_transfer = user_id.has_group('stock.group_stock_picking_wave')
        #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
        # wave_picking_count = stock_picking_batch_obj.search_count(
        #     [('state', '=', 'in_progress'), ('company_id', '=', request.env.user.company_id.id),
        #      ('is_wave', '=', True)]) if wave_transfer else 0
        if wave_transfer:
            wave_picking_count = stock_picking_batch_obj.search_count(
                [('state', '=', 'in_progress'),('is_wave', '=', True)]) if wave_transfer else 0
            res.append({
                "id": 0,
                "name": "Wave Transfers",
                "code": "",
                "sequence": 0,
                "count_picking_draft": 0,
                "count_picking_waiting": 0,
                "count_picking_ready": wave_picking_count,
                "count_picking_late": 0,
                "count_picking": 0,
                "count_picking_backorders": 0,
            })
        return res

    @staticmethod
    def _get_dashboard_values(self):
        product_template_obj = request.env['product.template'].search([('type', 'in', ['consu', 'product'])])
        user_id, is_admin = self._get_user_stock_group(self)

        res = {}

        sum_qty_available = 0
        # sum_virtual_available = 0
        sum_incoming_qty = 0
        sum_outgoing_qty = 0
        sum_batch_picking_qty = 0
        sum_wave_picking_qty = 0

        domain = [
            ('date', '>=', datetime.now().strftime('%Y-%m-%d 00:00:00')),
            ('date', '<=', datetime.now().strftime('%Y-%m-%d 23:59:59'))
        ]

        # stock_move_line_obj = request.env['stock.move.line']
        stock_move_line_objs = request.env['stock.move.line'].search(domain)

        # sum_incoming_qty = stock_move_line_obj.search_count(
        #     domain + [('picking_id.picking_type_id.code', '=', 'incoming')]
        # )
        # sum_outgoing_qty = stock_move_line_obj.search_count(
        #     domain + [('picking_id.picking_type_id.code', '=', 'outgoing')]
        # )

        for stock_move_line_obj in stock_move_line_objs:
            # Transfers calculation
            if is_admin == 0:
                if stock_move_line_obj.sudo().picking_id.user_id.id == user_id.id:
                    if stock_move_line_obj.picking_id.picking_type_id.code == "incoming":
                        # NOTE: qty_done in v16 is quantity in v17
                        sum_incoming_qty += stock_move_line_obj.quantity
                    elif stock_move_line_obj.picking_id.picking_type_id.code == "outgoing":
                        sum_outgoing_qty += stock_move_line_obj.quantity
            else:
                if stock_move_line_obj.picking_id.picking_type_id.code == "incoming":
                    sum_incoming_qty += stock_move_line_obj.quantity
                elif stock_move_line_obj.picking_id.picking_type_id.code == "outgoing":
                    sum_outgoing_qty += stock_move_line_obj.quantity

            # Batch & Wave Pickings calculation
            if stock_move_line_obj.batch_id:
                if is_admin == 0:
                    if stock_move_line_obj.sudo().batch_id.user_id.id == user_id.id:
                        if not stock_move_line_obj.batch_id.is_wave:
                            sum_batch_picking_qty += stock_move_line_obj.quantity
                        elif stock_move_line_obj.batch_id.is_wave:
                            sum_wave_picking_qty += stock_move_line_obj.quantity
                else:
                    if not stock_move_line_obj.batch_id.is_wave:
                        sum_batch_picking_qty += stock_move_line_obj.quantity
                    elif stock_move_line_obj.batch_id.is_wave:
                        sum_wave_picking_qty += stock_move_line_obj.quantity

        for prod_temp in product_template_obj:
            sum_qty_available += prod_temp.qty_available
            # sum_virtual_available += prod_temp.virtual_available
            # sum_incoming_qty += prod_temp.incoming_qty
            # sum_outgoing_qty += prod_temp.outgoing_qty

        res.update({
            'sum_qty_available': sum_qty_available,
            # 'sum_virtual_available': sum_virtual_available,
            'sum_incoming_qty': sum_incoming_qty,
            'sum_outgoing_qty': sum_outgoing_qty,
            'sum_batch_picking_qty': sum_batch_picking_qty,
            'sum_wave_picking_qty': sum_wave_picking_qty,
        })

        res.update({"to_process_count": self._get_picking_fields(self)})
        res.update({"warehouse_id": [str(user_id.warehouse_id.id),
                                     user_id.warehouse_id.name] if user_id.warehouse_id else []})
        res.update({"wms_licensing_key": request.env['ir.config_parameter'].sudo().get_param(
            'bista_wms_api.wms_licensing_key') or ""})

        # Pass 'quality_modules_installed' as False by default to be changed in inherited function later.
        res.update({'quality_modules_installed': False})

        return res

    @validate_token
    @http.route("/api/get_dashboard_today_stock_and_receipt", type="http", auth="none", methods=["GET"], csrf=False)
    def get_dashboard_today_stock_and_receipt(self, **payload):
        """Get Stock, Transfers & Receipt for Current Date for Dashboard."""

        _logger.info("/api/get_dashboard_today_stock_and_receipt payload: %s", payload)

        try:
            res = self._get_dashboard_values(self)

            return valid_response(res)
        except Exception as e:
            _logger.exception("Error while getting stock, transfers & receipt of dashboard for payload: %s", payload)
            error_msg = 'Error while getting stock, transfers & receipt of dashboard.'
            return invalid_response('bad_request', error_msg, 200)

    @validate_token
    @http.route("/api/get_picking_move_ids", type="http", auth="none", methods=["GET"], csrf=False)
    def get_picking_move_ids(self, **payload):
        """
            NOTE: DEPRECATED API for now, might be used later on.
            Gets the name of a stock_picking record from request and
            returns that specific stock_picking record's operations details.
            @:param barcode
            @:returns only the stock.move records related to the stock.picking record.
        """

        response_data = {}
        payload_data = payload

        if 'barcode' in payload_data:
            if payload_data['barcode']:
                stock_picking_obj = request.env['stock.picking'].sudo().search(
                    [('name', '=', payload_data.get('barcode'))])
                if stock_picking_obj:
                    move_ids = stock_picking_obj.move_ids_without_package.sudo().read(
                        ['name', 'product_uom_qty', 'quantity_done'])
                    response_data.update({
                        'id': stock_picking_obj.id,
                        'name': stock_picking_obj.name,
                        'move_ids': move_ids
                    })
                    return valid_response(response_data)
                else:
                    return invalid_response('not_found', 'No Picking record found.')
            else:
                return invalid_response('not_found', 'No barcode was provided.', 200)
        else:
            # ToDo: return all data in Ready state instead of invalid_response()
            return invalid_response('not_found', 'No barcode was provided.', 200)

    @staticmethod
    def get_picking_detail_response_data(self, response_data, stock_picking_objs):
        for stock_picking_obj in stock_picking_objs:
            move = []
            move_line = []
            # NOTE: transferred to bista_wms_sales_extension
            # sale_id = stock_picking_obj.sale_id.id if stock_picking_obj.sale_id else 0
            # NOTE: transfered to bista_wms_api_purchase_extension
            # purchase_id = stock_picking_obj.purchase_id.id if stock_picking_obj.purchase_id else 0
            rfid_tag = stock_picking_obj.rfid_tag.name if 'rfid_tag' in stock_picking_obj._fields else ""
            for move_id in stock_picking_obj.move_ids_without_package:
                move.append({
                    'id': move_id.id,
                    'product_id': move_id.product_id.id,
                    'product': move_id.product_id.display_name,
                    'location_id': [str(move_id.location_id.id),
                                    move_id.location_id.complete_name] if move_id.location_id else [],
                    'move_line_ids': move_id.move_line_ids.ids,
                    "product_packaging": [str(move_id.product_packaging_id.id),
                                          move_id.product_packaging_id.name] if move_id.product_packaging_id else [],
                    'product_code': move_id.product_id.default_code or "",
                    'description_picking': move_id.description_picking or "",
                    'product_uom_qty': move_id.product_uom_qty,
                    'state': dict(move_id._fields['state'].selection).get(move_id.state),
                })

            # move_ids = stock_picking_obj.move_ids_without_package.read([
            #     'name', 'description_picking', 'product_uom_qty', 'state'
            # ])
            # for move_id in move_ids:
            #     move_id['state'] = dict(stock_picking_obj.move_ids_without_package._fields['state'].selection).get(move_id['state'])
            for line_id in stock_picking_obj.move_line_ids:
                quant_line = []

                if not ast.literal_eval(request.env['ir.config_parameter'].sudo().get_param('bista_wms_api.restrict_stock_quants_in_location', 'False')):
                    stock_quants = request.env['stock.quant'].search([
                        ('product_id', '=', line_id.product_id.id), ('quantity', '>=', 0)
                    ])
                    product_stock_quant_ids = stock_quants.filtered(
                        lambda q: q.company_id in request.env.companies and q.location_id.usage == 'internal'
                    )

                    for quant_id in product_stock_quant_ids:
                        rfid = quant_id.lot_id.rfid_tag.name if 'rfid_tag' in quant_id.lot_id._fields else ""
                        quant_line.append({
                            'id': quant_id.id,
                            'location': quant_id.location_id.complete_name,
                            'lot_serial': quant_id.lot_id.name if quant_id.lot_id else "",
                            'rfid_tag': rfid or "",
                            'on_hand_quantity': quant_id.quantity,
                        })
                
                move_line.append({
                    'id': line_id.id,
                    'product_id': line_id.product_id.id,
                    'product': line_id.product_id.name,
                    'lot_id': [str(line_id.lot_id.id), line_id.lot_id.name] if line_id.lot_id else [],
                    'tracking': line_id.product_id.tracking,
                    'location_id': [str(line_id.location_id.id),
                                    line_id.location_id.complete_name] if line_id.location_id else [],
                    'location_dest_id': [str(line_id.location_dest_id.id),
                                            line_id.location_dest_id.complete_name] if line_id.location_dest_id else [],
                    'move_id': line_id.move_id.id,
                    'product_packages': [str(line_id.result_package_id.id),
                                         line_id.result_package_id.name] if line_id.result_package_id else [],
                    'product_code': line_id.product_id.default_code or "",
                    # 'product_uom_qty': line_id.reserved_uom_qty,  #NOTE:reserved_uom_qty not available in v17
                    'product_uom_qty': line_id.move_id.product_uom_qty,
                    # 'quantity_done': line_id.qty_done, # NOTE: qty_done is quantity in v17
                    'quantity_done': line_id.quantity,
                    'quant_ids': quant_line,
                })

            response_data.append({
                'id': stock_picking_obj.id,
                'name': stock_picking_obj.name,
                'rfid_tag': rfid_tag or "",
                'source_doc': stock_picking_obj.origin if stock_picking_obj.origin else "",
                'schedule_date': stock_picking_obj.scheduled_date or "",
                'deadline': stock_picking_obj.date_deadline or "",
                'done_date': stock_picking_obj.date_done or "",
                'restrict_scan_source_location': stock_picking_obj.picking_type_id.restrict_scan_source_location if 'restrict_scan_source_location' in stock_picking_obj.picking_type_id._fields else "",
                'restrict_scan_tracking_number': stock_picking_obj.picking_type_id.restrict_scan_tracking_number if 'restrict_scan_tracking_number' in stock_picking_obj.picking_type_id._fields else "",
                'partner_id': [str(stock_picking_obj.partner_id.id),
                               stock_picking_obj.partner_id.name] if stock_picking_obj.partner_id else [],
                'user_id': [str(stock_picking_obj.user_id.id),
                            stock_picking_obj.user_id.name] if stock_picking_obj.user_id else [],
                'location_id': [str(stock_picking_obj.location_id.id),
                                stock_picking_obj.location_id.display_name] if stock_picking_obj.location_id else [],
                'location_dest_id': [str(stock_picking_obj.location_dest_id.id),
                                     stock_picking_obj.location_dest_id.display_name] if stock_picking_obj.location_dest_id else [],
                'operation_type_id': [str(stock_picking_obj.picking_type_id.id),
                                      stock_picking_obj.picking_type_id.name] if stock_picking_obj.picking_type_id else [],
                'operation_type': stock_picking_obj.operation_type if stock_picking_obj.operation_type else "",
                'warehouse_id': [str(stock_picking_obj.picking_type_id.warehouse_id.id),
                                 stock_picking_obj.picking_type_id.warehouse_id.name] if stock_picking_obj.picking_type_id.warehouse_id else [],
                'group_id': str(stock_picking_obj.group_id.id) if stock_picking_obj.group_id else "",
                # NOTE: transfered to bista_wms_api_sale_delivery_extension
                # 'procurement_group': [str(stock_picking_obj.group_id.id),
                #                       str(stock_picking_obj.group_id.name)] if stock_picking_obj.group_id else [],
                # 'sale_id': sale_id,
                # NOTE: transfered to bista_wms_api_purchase_extension
                # 'purchase_id': purchase_id,
                'priority': dict(stock_picking_obj._fields['priority'].selection).get(
                    stock_picking_obj.priority),
                'company': stock_picking_obj.company_id.name,
                'company_id': [str(stock_picking_obj.company_id.id),
                                stock_picking_obj.company_id.name] if stock_picking_obj.company_id else [],
                'move_ids': move,
                'move_line_ids': move_line,
                # 'batch_id': [str(stock_picking_obj.batch_id.id or ""), stock_picking_obj.batch_id.name or ""],
                'create_backorder': stock_picking_obj.picking_type_id.create_backorder,
                'state': stock_picking_obj.state,
                'shipping_policy': stock_picking_obj.move_type,
                'create_uid': [str(stock_picking_obj.create_uid.id),
                               stock_picking_obj.create_uid.name] if stock_picking_obj.create_uid else [],
                'create_date': stock_picking_obj.create_date,
                'write_uid': [str(stock_picking_obj.write_uid.id),
                              stock_picking_obj.write_uid.name] if stock_picking_obj.write_uid else [],
                'write_date': stock_picking_obj.write_date,
                'can_be_validated': True,
                'create_new_lot': stock_picking_obj.picking_type_id.use_create_lots,
                'use_existing_lot': stock_picking_obj.picking_type_id.use_existing_lots
            })
        # response_data = sorted(response_data, key=lambda i: i['group_id'][0], reverse= True)
        return response_data

    @validate_token
    @http.route("/api/get_picking_detail", type="http", auth="none", methods=["GET"], csrf=False)
    def get_picking_detail(self, **payload):
        """
            Gets the name of a stock_picking record from request and
            returns that specific stock_picking record's details.
            If name of a stock_picking not in request then returns
            all the stock_picking record details of ready state.
        """

        _logger.info("/api/get_picking_detail payload: %s", payload)

        try:
            response_data = []
            payload_data = payload
            domain = []
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                domain += filter_by_last_sync_time('stock.picking', payload_data)

            stock_picking = request.env['stock.picking'].search(domain)
            stock_picking_objs = False
            multi_steps_routing = request.env.user.has_group('stock.group_adv_location')

            user_id, is_admin = self._get_user_stock_group(self)

            if 'barcode' in payload_data or 'picking_id' in payload_data or 'picking_type_id' in payload_data:
                # domain = [('state', '=', 'assigned')]
                if 'barcode' in payload_data:
                    if payload_data['barcode']:
                        stock_picking_domain = [('name', '=', payload_data.get('barcode'))]
                        if 'rfid_tag' in stock_picking._fields:
                            stock_picking_domain = ['|', ('name', '=', payload_data.get('barcode')),
                                                    ('rfid_tag.name', '=', payload_data.get('barcode'))]
                        if is_admin == 0:
                            stock_picking_domain = stock_picking_domain + [('user_id', '=', user_id.id)]
                        stock_picking_objs = stock_picking.sudo().search(stock_picking_domain)
                elif 'picking_id' in payload_data:
                    if payload_data['picking_id']:
                        stock_picking_domain = [
                            ('id', '=', int(payload_data['picking_id']))
                        ]
                        if is_admin == 0:
                            stock_picking_domain = stock_picking_domain + [('user_id', '=', user_id.id)]
                        stock_picking_objs = stock_picking.sudo().search(stock_picking_domain)
                elif 'picking_type_id' in payload_data:
                    if payload_data['picking_type_id']:
                        stock_picking_domain = [
                            ('state', '=', 'assigned'),
                            ('picking_type_id', '=', int(payload_data.get('picking_type_id')))
                        ]
                        if is_admin == 0:
                            stock_picking_domain = stock_picking_domain + [('user_id', '=', user_id.id)]
                        stock_picking_objs = stock_picking.sudo().search(stock_picking_domain)
            else:
                if not multi_steps_routing: 
                    #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                    # stock_picking_domain = [('state', '=', 'assigned'),
                    #                         ('company_id', '=', request.env.user.company_id.id)]
                    stock_picking_domain = [('state', '=', 'assigned')]
                else:
                    # stock_picking_domain = [('state', 'in', ['assigned', 'waiting']),
                    #                         ('company_id', '=', request.env.user.company_id.id)]
                    stock_picking_domain = [('state', 'in', ['assigned', 'waiting'])]
                if is_admin == 0:
                    if user_id.warehouse_id.reception_steps in ['two_steps',
                                                                'three_steps'] or user_id.warehouse_id.delivery_steps in [
                        'pick_ship', 'pick_pack_ship']:
                        stock_picking_domain = stock_picking_domain + \
                                               [('user_id', '=', user_id.id)]
                    else:
                        # stock_picking_domain = [('state', '=', 'assigned'), (
                        #     'company_id', '=', request.env.user.company_id.id), ('user_id', '=', user_id.id)]
                        stock_picking_domain = [('state', '=', 'assigned'), ('user_id', '=', user_id.id)]

                if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                    stock_picking_domain += filter_by_last_sync_time('stock.picking', payload_data)

                stock_picking_objs = stock_picking.sudo().search(stock_picking_domain, order='id')

            if stock_picking_objs:
                response_data = self.get_picking_detail_response_data(self, response_data, stock_picking_objs)

                return valid_response(response_data)
            else:
                return invalid_response('not_found', 'No Picking record found.')
        except Exception as e:
            _logger.exception("Error while getting picking details for payload: %s", payload)
            error_msg = 'Error while getting picking details.'
            return invalid_response('bad_request', error_msg, 200)

    @validate_token
    @http.route('/api/report/download', type='http', auth="none", methods=["GET"], csrf=False)
    def api_report_download(self, report_name=None, report_type=None, options=None, context=None):
        """This function is used by 'action_manager_report.js' in order to trigger the download of
        a pdf/controller report.

        @:param report_name: a javascript array JSON.stringified containing report internal url
        @:param report_type: a string that contains the report type to print.
        @:param options: a JSON containing the details options for printing a report.
        @:returns: Response with an attachment header

        """
        _logger.info("/api/report/download report_name: %s, report_type: %s, options: %s, context: %s",
                     report_name, report_type, options, context)
        try:
            if report_name and report_type:
                data = "[" + report_name + "," + report_type + "]"
                requestcontent = json.loads(data)
                url, type = requestcontent[0], requestcontent[1]
                reportname = '???'
                try:
                    if type in ['qweb-pdf', 'qweb-text']:
                        converter = 'pdf' if type == 'qweb-pdf' else 'text'
                        extension = 'pdf' if type == 'qweb-pdf' else 'txt'

                        pattern = '/report/pdf/' if type == 'qweb-pdf' else '/report/text/'
                        reportname = url.split(pattern)[1].split('?')[0]

                        docids = None
                        if '/' in reportname:
                            reportname, docids = reportname.split('/')

                            # NOTE: Check if the picking id exists for Picking Operation & Delivery Slip reports
                            if docids and reportname in ['stock.report_deliveryslip', 'stock.report_picking']:
                                ids = [int(x) for x in docids.split(",")]
                                stock_picking_obj = request.env['stock.picking'].search([('id', 'in', ids)])
                                if not stock_picking_obj:
                                    return invalid_response('bad_request', 'Provided picking not found.', 200)

                        if docids:
                            # Generic report:
                            response = ReportController.report_routes(self, reportname=reportname, docids=docids,
                                                                      converter=converter, context=context)
                        else:
                            # Particular report:
                            # data = dict(url_decode(url.split('?')[1]).items())  # decoding the args represented in JSON
                            # data = dict(url_decode(options).items())  # decoding the args represented in JSON
                            # data = json.loads(options)
                            if 'context' in data:
                                # context, data_context = json.loads(context or '{}'), json.loads(data.pop('context'))
                                context, data_context = json.loads(context or '{}'), json.loads(options)
                                context = json.dumps({**context, **data_context})
                            response = ReportController.report_routes(self, reportname=reportname, converter=converter,
                                                                      context=context, **json.loads(options))

                        report = request.env['ir.actions.report']._get_report_from_name(reportname)
                        filename = "%s.%s" % (report.name, extension)

                        if docids:
                            ids = [int(x) for x in docids.split(",")]
                            obj = request.env[report.model].browse(ids)
                            if report.print_report_name and not len(obj) > 1:
                                report_name = safe_eval(report.print_report_name, {'object': obj, 'time': time})
                                filename = "%s.%s" % (report_name, extension)
                        response.headers.add('Content-Disposition', content_disposition(filename))
                        return response
                    else:
                        _logger.exception("The report_type in request is not defined properly.")
                        return invalid_response('bad_request',
                                                'The report_type in request is not defined properly.', 200)
                except Exception as e:
                    _logger.exception("Error while generating report %s", reportname)
                    # se = _serialize_exception(e)
                    # error = {
                    #     'code': 200,
                    #     'message': "Odoo Server Error",
                    #     'data': se
                    # }
                    # return request.make_response(html_escape(json.dumps(error)))
                    error_message = "Error while generating report '" + reportname + "'"
                    return invalid_response('bad_request', error_message, 200)
            else:
                return invalid_response('bad_request', 'Report Name or Type was not provided.', 200)
        except Exception as e:
            _logger.exception(
                "Error while generating Report for report_name: %s, report_type: %s, options: %s, context: %s",
                report_name, report_type, options, context)
            error_msg = 'Error while generating Report.'
            return invalid_response('bad_request', error_msg, 200)

    @validate_token
    @http.route('/api/label/download', type='http', auth="none", methods=["GET"], csrf=False)
    def api_label_download(self, context=None, **payload):
        _logger.info("/api/label/download payload: %s, context: %s", payload, context)

        try:
            payload_data = payload

            if 'picking_id' in payload_data and 'batch_id' in payload_data:
                return invalid_response('bad_request', "Both Picking or Batch id should not be provided.", 200)
            elif 'picking_id' in payload_data or 'batch_id' in payload_data:
                context = json.loads(context)

                if 'picking_id' in payload_data:
                    picking_id = int(payload_data.get('picking_id'))
                    active_id = picking_id
                    stock_picking_obj = request.env['stock.picking'].sudo().browse(picking_id)
                    move_lines = stock_picking_obj.move_ids_without_package.move_line_ids

                elif 'batch_id' in payload_data:
                    batch_id = int(payload_data.get('batch_id'))
                    active_id = batch_id
                    stock_picking_batch_obj = request.env['stock.picking.batch'].sudo().browse(batch_id)
                    move_lines = stock_picking_batch_obj.move_line_ids

                stock_picking_move_lines_products = []
                for move_line in move_lines:
                    stock_picking_move_lines_products.append(move_line.product_id.id)

                if payload_data.get('is_lot_label') and eval(payload_data.get('is_lot_label')):
                    stock_picking_move_lines_lots = []
                    for move_line in move_lines:
                        if move_line.lot_id:
                            stock_picking_move_lines_lots.append(move_line.lot_id.id)

                new_context = dict(context, **{
                    "allowed_company_ids": request.env.user.company_ids.ids,
                    "contact_display": "partner_address", "active_model": "stock.picking",
                    "active_id": active_id, "active_ids": [active_id],
                    "default_product_ids": stock_picking_move_lines_products,
                    "default_move_line_ids": move_lines.ids,
                    "default_move_quantity": "move" #"default_picking_quantity": "picking" # NOTE: picking_quantity is move_quantity in v17
                })

                # NOTE: create new layout wizard through code & get the id to pass in the options
                if payload_data.get('is_lot_label') and not eval(payload_data.get('is_lot_label')):
                    prod_label_wiz = request.env['product.label.layout'].sudo().with_context(new_context).create({
                        "print_format": 'dymo',
                        "product_ids": [(6, 0, stock_picking_move_lines_products)],
                        "move_quantity": 'move'  # "picking_quantity": 'picking'
                    })
                    prod_label_wiz_rec = request.env['product.label.layout'].browse(prod_label_wiz.id)
                    prod_label_wiz_process_data = prod_label_wiz_rec.with_context(context).process()
                    if prod_label_wiz_process_data.get('report_name') and prod_label_wiz_process_data.get(
                            'report_type') and prod_label_wiz_process_data.get('data'):
                        report_name = '"/report/pdf/' + prod_label_wiz_process_data['report_name'] + '"'
                        report_type = '"' + prod_label_wiz_process_data['report_type'] + '"'
                        options = prod_label_wiz_process_data['data']
                        return self.api_report_download(report_name=report_name, report_type=report_type,
                                                        options=json.dumps(options), context=json.dumps(new_context))

                if payload_data.get('is_lot_label') and eval(payload_data.get('is_lot_label')):
                    label_quantity = payload_data.get('label_quantity').lower()
                    lot_label_wiz = request.env['lot.label.layout'].sudo().with_context(new_context).create({
                        "label_quantity": label_quantity,
                        "print_format": '4x12',
                    })
                    lot_label_wiz_rec = request.env['lot.label.layout'].browse(lot_label_wiz.id)
                    lot_label_wiz_process_data = lot_label_wiz_rec.with_context(context).process()
                    if lot_label_wiz_process_data.get('report_name') and lot_label_wiz_process_data.get(
                            'report_type') and lot_label_wiz_process_data.get('data'):
                        report_name = '"/report/pdf/' + lot_label_wiz_process_data['report_name'] + '"'
                        report_type = '"' + lot_label_wiz_process_data['report_type'] + '"'
                        all_docids = []
                        if 'batch_id' in payload_data and payload_data.get('batch_id'):
                            doc_picking_ids = request.env['stock.picking.batch'].sudo().search(
                                [('id', 'in', [batch_id])]).picking_ids
                        else:
                            doc_picking_ids = request.env['stock.picking'].sudo().search([('id', 'in', [picking_id])])
                        if doc_picking_ids and label_quantity == 'lots':
                            all_docids = doc_picking_ids.move_line_ids.lot_id.ids
                        else:
                            uom_categ_unit = request.env.ref('uom.product_uom_categ_unit')
                            quantity_by_lot = defaultdict(int)
                            for move_line in doc_picking_ids.move_line_ids:
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

                        if not all_docids:
                            return invalid_response(typ='bad_request', status=200,
                                                    message="Error while generating Lot Labels. No available lot to print.")
                        options = {'all_docids': all_docids}

                        return self.api_report_download(report_name=report_name, report_type=report_type,
                                                    options=json.dumps(options), context=json.dumps(new_context))
                else:
                    return invalid_response(typ='bad_request', status=200,
                                            message="Error while generating Labels. Please contact Administrator")
            else:
                return invalid_response('bad_request', "Picking or Batch id was not provided.", 200)
        except Exception as e:
            _logger.exception("Error while generating labels for payload: %s", payload)
            # se = _serialize_exception(e)
            # _logger.exception(se)
            error_msg = 'Error while generating Product Labels.'
            # if "name" in e:
            #     error_msg += "Reason:\n" + e.name
            # error_msg = error_msg.replace('\n', ' ')
            return invalid_response('bad_request', error_msg, 200)

    @validate_token
    @http.route("/api/user_detail", type="http", auth="none", methods=["GET"], csrf=False)
    def get_user_detail(self, **payload):
        _logger.info("/api/user_detail GET payload: %s", payload)

        try:
            access_token = request.httprequest.headers.get("access-token")
            user_id = request.env['api.access_token'].sudo().search([('token', '=', access_token)], limit=1).user_id
            if user_id and request.httprequest.method == 'GET':
                user_details = {
                    'name': user_id.name or "",
                    'email': user_id.login or "",
                    'image': user_id.image_1920.decode("utf-8") if user_id.image_1920 else "",
                    "warehouse_id": [str(user_id.warehouse_id.id),
                                     user_id.warehouse_id.name] if user_id.warehouse_id else [],
                }
                # NOTE: ADD to_process_count to the User Profile
                user_details.update({"to_process_count": self._get_picking_fields(self)})
                return valid_response(user_details)
            else:
                return invalid_response('not_found', 'No User Data Found.')
        except Exception as e:
            _logger.exception("Error while getting user data for payload: %s", payload)
            error_msg = 'Error while getting user data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def get_product_detail_response_data(self, domain, payload_data):

        product_product = request.env['product.product'].search(domain)
        stock_lot = request.env['stock.lot'].search(domain)

        if 'barcode' in payload_data:
            if payload_data['barcode']:
                # get product.product object search by barcode
                product_product_domain = [('barcode', '=', payload_data.get('barcode'))]
                if 'rfid_tag' in product_product._fields:
                    product_product_domain = ['|', ('barcode', '=', payload_data.get('barcode')),
                                              ('rfid_tag.name', '=', payload_data.get('barcode'))]
                product_product_objs = product_product.search(product_product_domain, limit=1)
                if product_product_objs:
                    product_template_objs = product_product_objs.product_tmpl_id
                    product_template_img = product_template_objs.image_1920.decode(
                        "utf-8") if product_template_objs.image_1920 else ""
                elif not product_product_objs:
                    # get product.product object from stock.lot
                    stock_lot_domain = [('name', '=', payload_data.get('barcode'))]
                    if 'rfid_tag' in product_product._fields:
                        stock_lot_domain = ['|', ('name', '=', payload_data.get('barcode')),
                                            ('rfid_tag.name', '=', payload_data.get('barcode'))]
                    product_product_objs = stock_lot.sudo().search(stock_lot_domain, limit=1).product_id
                    if product_product_objs:
                        product_template_objs = product_product_objs.product_tmpl_id
                        product_template_img = product_template_objs.image_1920.decode(
                            "utf-8") if product_template_objs.image_1920 else ""
                    else:
                        # return invalid_response('not_found', 'No product found for this barcode.')
                        return {"status": False, 'code': "not_found", 'message': "No product found for this barcode"}
            else:
                # return invalid_response('not_found', 'No product found for this barcode.')
                return {"status": False, 'code': "not_found", 'message': "No product found for this barcode"}
        else:
            domain.append(('type', 'in', ['consu', 'product']))
            product_template_objs = request.env['product.template'].search(domain)
            product_template_img = ""

        if product_template_objs:
            response_data = []
            stock_putaway = request.env['stock.putaway.rule']
            stock_storage_capacity = request.env['stock.storage.category.capacity']

            for product in product_template_objs:
                barcode = []
                rfid_tags = []
                packaging_line = []
                product_variants = []
                for product_variant in product.product_variant_ids:
                    variant_values = []
                    rfid_tag_variant = []
                    barcode_variant = []
                    if product_variant.barcode:
                        barcode.append(product_variant.barcode)
                        barcode_variant.append(product_variant.barcode)
                    if 'rfid_tag' in product_variant._fields:
                        if product_variant.rfid_tag:
                            rfid_tags.append(product_variant.rfid_tag.name)
                            rfid_tag_variant.append(product_variant.rfid_tag.name)
                    stock_lot_variant_obj = request.env['stock.lot'].search(
                        [('product_id', '=', product_variant.id), ('product_id.barcode', '=', product_variant.barcode)])
                    lot_serial_variant = stock_lot_variant_obj.mapped('name')
                    if product_variant.product_variant_count >= 1:
                        for variant_value in product_variant.product_template_variant_value_ids:
                            variant_values.append(f'{variant_value.attribute_id.name}:{variant_value.name}')
                    product_variants.append({'id': product_variant.id,
                                             'name': product.display_name,
                                             'barcode': barcode_variant + lot_serial_variant + rfid_tag_variant,
                                             'variant_values': variant_values})
                #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                # stock_quants = request.env['stock.quant'].search([
                #     ('product_id.product_tmpl_id', '=', product.id), ('quantity', '>=', 0),
                #     ('location_id.usage', '=', 'internal'),
                #     ('company_id', '=', request.env.user.company_id.id)
                # ])
                stock_quants = request.env['stock.quant'].search([
                    ('product_id.product_tmpl_id', '=', product.id), ('quantity', '>=', 0),
                    ('location_id.usage', '=', 'internal')])
                stock_quants_on_hand_qty = stock_quants.mapped('quantity')
                stock_quants_available_quantity_qty = stock_quants.mapped('available_quantity')

                quant_detail = stock_quants.sudo().read([
                    'location_id', 'product_id', 'lot_id', 'package_id', 'owner_id', 'product_categ_id',
                    'quantity', 'reserved_quantity', 'available_quantity',
                    'inventory_quantity', 'inventory_quantity_auto_apply', 'inventory_diff_quantity',
                    'inventory_date'
                ])
                for quant in quant_detail:
                    if not quant['location_id']:
                        quant['location_id'] = []
                    else:
                        quant['location_id'] = list(quant['location_id'])
                        quant['location_id'][0] = str(quant['location_id'][0])
                    if not quant['product_id']:
                        quant['product_id'] = []
                    else:
                        quant['product_id'] = list(quant['product_id'])
                        quant['product_id'][0] = str(quant['product_id'][0])
                    if not quant['lot_id']:
                        quant['lot_id'] = []
                    else:
                        quant['lot_id'] = list(quant['lot_id'])
                        quant['lot_id'][0] = str(quant['lot_id'][0])
                    if not quant['package_id']:
                        quant['package_id'] = []
                    else:
                        quant['package_id'] = list(quant['package_id'])
                        quant['package_id'][0] = str(quant['package_id'][0])
                    if not quant['owner_id']:
                        quant['owner_id'] = []
                    else:
                        quant['owner_id'] = list(quant['owner_id'])
                        quant['owner_id'][0] = str(quant['owner_id'][0])
                    if not quant['product_categ_id']:
                        quant['product_categ_id'] = []
                    else:
                        quant['product_categ_id'] = list(quant['product_categ_id'])
                        quant['product_categ_id'][0] = str(quant['product_categ_id'][0])

                #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                # putaway_count = stock_putaway.sudo().search_count([
                #     ('company_id', '=', request.env.user.company_id.id),
                #     '|', ('product_id.product_tmpl_id', '=', product.id),
                #     ('category_id', '=', product.categ_id.id)
                # ])
                putaway_count = stock_putaway.sudo().search_count([
                    '|', ('product_id.product_tmpl_id', '=', product.id),
                    ('category_id', '=', product.categ_id.id)
                ])
                # storage_capacity_count = stock_storage_capacity.sudo().search_count([
                #     ('product_id', 'in', product.product_variant_ids.ids),
                #     ('company_id', '=', request.env.user.company_id.id)
                # ])
                storage_capacity_count = stock_storage_capacity.sudo().search_count([
                    ('product_id', 'in', product.product_variant_ids.ids)
                ])
                stock_lot_obj = stock_lot.search([('product_id', 'in', product.product_variant_ids.ids)])
                lot_serial = stock_lot_obj.mapped('name')
                if 'rfid_tag' in stock_lot._fields:
                    for lot_obj in stock_lot_obj:
                        if lot_obj.rfid_tag:
                            rfid_tags.append(lot_obj.rfid_tag.name)
                # packaging_type details:
                user_id, is_admin = self._get_user_stock_group(self)
                packaging_enabled = user_id.has_group('product.group_stock_packaging')
                if packaging_enabled:
                    for packaging in product.packaging_ids:
                        packaging_line.append({
                            'name': packaging.name,
                            'package_type_id': [str(packaging.package_type_id.id),
                                                str(packaging.package_type_id.name)] if packaging.package_type_id else [],
                            'qty': packaging.qty,   
                            # NOTE: transferred to bista_wms_sales_extensions
                            # 'sales': str(packaging.sales or ""),
                            # NOTE: transfered to bista_wms_api_purchase_extension
                            # 'purchase': str(packaging.purchase or ""),
                        })

                response_data.append({
                    'id': product.id,
                    'product_name': product.name,
                    'tracking': product.tracking,
                    'product_code': product.default_code or "",
                    'barcode': barcode + lot_serial + rfid_tags,
                    'prod_barcode': barcode,
                    'lot_serial_number': lot_serial,
                    'rfid_tags': rfid_tags,
                    'expiration_date': product.use_expiration_date if 'use_expiration_date' in product._fields else False,
                    'inventory_location': product.property_stock_inventory.complete_name or "",
                    'variant': product.product_variant_count,
                    'product_variants': product_variants,
                    'on_hand': sum(stock_quants_on_hand_qty) if stock_quants else 0,
                    'available_quantity': sum(stock_quants_available_quantity_qty) if stock_quants else 0,
                    'on_hand_details': quant_detail,
                    # NOTE: transfered to bista_wms_api_purchase_extension
                    # 'purchase_unit': product.purchased_product_qty,
                    # NOTE: transferred to bista_wms_sales_extensions
                    # 'sold_unit': product.sales_count,
                    'putaway': putaway_count,
                    'storage_capacity': storage_capacity_count,
                    'product_in': product.nbr_moves_in,
                    'product_out': product.nbr_moves_out,
                    'packaging_line': packaging_line,
                    'image': product_template_img or "",
                    'image_url':'/web/image?model=product.template&id={}&field=image_128'.format(product.id),
                    'list_price': product.list_price,
                    'company_id': [str(product.company_id.id), product.company_id.name] if product.company_id else [],
                    'categ_id': [str(product.categ_id.id), product.categ_id.name] if product.categ_id else [],
                })

            # return valid_response(response_data)
            return {"status": True, 'data': response_data}

        else:
            # return invalid_response('not_found', 'No product found.')
            return {"status": False, 'code': "not_found", 'message': "No product found"}

    @validate_token
    @http.route("/api/get_product_detail", type="http", auth="none", methods=["GET"], csrf=False)
    def get_product_detail(self, **payload):
        """
            Gets the barcode of a product from request and
            returns that specific product's location and quantity.
        """
        _logger.info("/api/get_product_detail payload: %s", payload)

        try:

            payload_data = payload
            domain = []
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                domain += filter_by_last_sync_time('product.product', payload_data)

            # TODO
            res = self.get_product_detail_response_data(self, domain, payload_data)

            if res['status']:
                return valid_response(res['data'])
            else:
                return invalid_response(res['code'], res['message'], 200)

        except Exception as e:
            _logger.exception("Error while getting product details for payload: %s", payload)
            error_msg = 'Error while getting product details.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def get_batch_detail_response_data(self, stock_picking_batch_objs, response_data):
        for stock_picking_batch_obj in stock_picking_batch_objs:
            picking = []
            move = []
            move_line = []
            for picking_id in stock_picking_batch_obj.picking_ids:
                rfid = picking_id.rfid_tag.name if 'rfid_tag' in picking_id._fields else ""
                picking.append({
                    'id': picking_id.id,
                    'name': picking_id.name,
                    'rfid_tag': rfid or "",
                    'source_doc': picking_id.origin if picking_id.origin else "",
                    'schedule_date': picking_id.scheduled_date or "",
                    'deadline': picking_id.date_deadline or "",
                    'done_date': picking_id.date_done or "",
                    'partner_id': [str(picking_id.partner_id.id),
                                   picking_id.partner_id.name] if picking_id.partner_id else [],
                    'location_id': [str(picking_id.location_id.id),
                                    picking_id.location_id.display_name] if picking_id.location_id else [],
                    'location_dest_id': [str(picking_id.location_dest_id.id),
                                         picking_id.location_dest_id.display_name] if picking_id.location_dest_id else [],
                    'operation_type_id': [str(picking_id.picking_type_id.id),
                                          picking_id.picking_type_id.name] if picking_id.picking_type_id else [],
                    'operation_type': picking_id.operation_type if picking_id.operation_type else "",
                    'restrict_scan_source_location': picking_id.picking_type_id.restrict_scan_source_location if 'restrict_scan_source_location' in picking_id.picking_type_id._fields else "",
                    'restrict_scan_tracking_number': picking_id.picking_type_id.restrict_scan_tracking_number if 'restrict_scan_tracking_number' in picking_id.picking_type_id._fields else "",
                    'priority': dict(picking_id._fields['priority'].selection).get(picking_id.priority),
                    'company': picking_id.company_id.name,
                    # NOTE: transferred to bista_wms_sales_extension
                    # 'sale_id': picking_id.sale_id.id if picking_id.sale_id else 0,
                    # NOTE: transfered to bista_wms_api_purchase_extension
                    # 'purchase_id': picking_id.purchase_id.id if picking_id.purchase_id else 0,
                    'state': dict(picking_id._fields['state'].selection).get(picking_id.state),
                    'shipping_policy': picking_id.move_type,
                    'create_uid': [str(picking_id.create_uid.id),
                                   picking_id.create_uid.name] if picking_id.create_uid else [],
                    'create_date': picking_id.create_date,
                    'write_uid': [str(picking_id.write_uid.id),
                                  picking_id.write_uid.name] if picking_id.write_uid else [],
                    'write_date': picking_id.write_date,
                })

            for move_id in stock_picking_batch_obj.move_ids:
                move.append({
                    'id': move_id.id,
                    'picking_id': move_id.picking_id.id,
                    'product_id': move_id.product_id.id,
                    'product': move_id.product_id.display_name,
                    'product_packaging': [str(move_id.product_packaging_id.id),
                                          move_id.product_packaging_id.name] if move_id.product_packaging_id else [],
                    'product_code': move_id.product_id.default_code or "",
                    'description_picking': move_id.description_picking or "",
                    'product_uom_qty': move_id.product_uom_qty,
                    'state': dict(move_id._fields['state'].selection).get(move_id.state),
                })

            for line_id in stock_picking_batch_obj.move_line_ids:
                quant_line = []

                stock_quants = request.env['stock.quant'].search([
                    ('product_id', '=', line_id.product_id.id), ('quantity', '>=', 0)
                ])
                product_stock_quant_ids = stock_quants.filtered(
                    lambda q: q.company_id in request.env.companies and q.location_id.usage == 'internal'
                )

                for quant_id in product_stock_quant_ids:
                    rfid = quant_id.lot_id.rfid_tag.name if 'rfid_tag' in quant_id.lot_id._fields else ""
                    quant_line.append({
                        'id': quant_id.id,
                        'location': quant_id.location_id.complete_name,
                        'lot_serial': quant_id.lot_id.name if quant_id.lot_id else "",
                        'rfid_tag': rfid or "",
                        'on_hand_quantity': quant_id.quantity,
                    })
                move_line.append({
                    'id': line_id.id,
                    'picking_id': line_id.picking_id.id,
                    'picking_name': line_id.picking_id.name,
                    'product_id': line_id.product_id.id,
                    'product': line_id.product_id.name,
                    'lot_id': line_id.lot_id.name if line_id.lot_id else [],
                    'product_packages': [str(line_id.result_package_id.id),
                                         line_id.result_package_id.name] if line_id.result_package_id else [],
                    'product_code': line_id.product_id.default_code or "",
                    # 'product_uom_qty': line_id.reserved_uom_qty, #NOTE: reserved_uom_qty is not available in v17
                    'product_uom_qty': line_id.move_id.product_uom_qty,
                    # 'quantity_done': line_id.qty_done, # NOTE: qty_done is quantity in v17
                    'quantity_done': line_id.quantity,
                    'quant_ids': quant_line,
                })

            response_data.append({
                'id': stock_picking_batch_obj.id,
                'name': stock_picking_batch_obj.name,
                'is_wave': stock_picking_batch_obj.is_wave,
                'schedule_date': stock_picking_batch_obj.scheduled_date or "",
                'company': stock_picking_batch_obj.company_id.name,
                'picking': picking,
                'move': move,
                'move_line': move_line,
                'state': dict(stock_picking_batch_obj._fields['state'].selection).get(
                    stock_picking_batch_obj.state),
                'create_uid': [str(stock_picking_batch_obj.create_uid.id),
                               stock_picking_batch_obj.create_uid.name] if stock_picking_batch_obj.create_uid else [],
                'create_date': stock_picking_batch_obj.create_date,
                'write_uid': [str(stock_picking_batch_obj.write_uid.id),
                              stock_picking_batch_obj.write_uid.name] if stock_picking_batch_obj.write_uid else [],
                'write_date': stock_picking_batch_obj.write_date,
            })
        return response_data

    @validate_token
    @http.route("/api/get_batch_detail", type="http", auth="none", methods=["GET"], csrf=False)
    def get_batch_detail(self, **payload):
        """
            Gets the name of a stock_picking_batch record from request and
            returns that specific stock_picking_batch record's details.
            If name of a stock_picking_batch not in request then returns
            all the stock_picking_batch record details of ready state.
        """

        _logger.info("/api/get_batch_picking_detail payload: %s", payload)

        try:
            response_data = []
            payload_data = payload
            stock_picking_batch_domain = []
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                stock_picking_batch_domain += filter_by_last_sync_time('stock.picking.batch', payload_data)
            stock_picking_batch = request.env['stock.picking.batch'].search(stock_picking_batch_domain)
            stock_picking_batch_objs = False

            user_id, is_admin = self._get_user_stock_group(self)

            if 'barcode' in payload_data or 'batch_id' in payload_data or \
                    'picking_type_id' in payload_data or 'is_wave' in payload_data:
                domain = [('state', '=', 'in_progress')]
                if 'barcode' in payload_data:
                    if payload_data['barcode']:
                        stock_picking_batch_domain = [('name', '=', payload_data.get('barcode'))]
                        if is_admin == 0:
                            stock_picking_batch_domain = stock_picking_batch_domain + [('user_id', '=', user_id.id)]
                        stock_picking_batch_objs = stock_picking_batch.sudo().search(stock_picking_batch_domain)
                elif 'batch_id' in payload_data:
                    if payload_data['batch_id']:
                        stock_picking_batch_domain = [
                            ('id', '=', int(payload_data['batch_id']))
                        ]
                        if is_admin == 0:
                            stock_picking_batch_domain = stock_picking_batch_domain + [('user_id', '=', user_id.id)]
                        stock_picking_batch_objs = stock_picking_batch.sudo().search(stock_picking_batch_domain)
                elif 'picking_type_id' in payload_data:
                    if payload_data['picking_type_id']:
                        domain += [('picking_type_id', '=', int(payload_data.get('picking_type_id')))]
                        if is_admin == 0:
                            domain += [('user_id', '=', user_id.id)]
                        stock_picking_batch_objs = stock_picking_batch.sudo().search(domain)
                elif 'is_wave' in payload_data:
                    if payload_data['is_wave']:
                        domain += [('is_wave', '=', int(payload_data.get('is_wave')))]
                        if is_admin == 0:
                            domain += [('user_id', '=', user_id.id)]
                        stock_picking_batch_objs = stock_picking_batch.sudo().search(domain)
            else:
                #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                # stock_picking_batch_domain = [('state', '=', 'in_progress'),
                #                               ('company_id', '=', request.env.user.company_id.id)]
                stock_picking_batch_domain = [('state', '=', 'in_progress')]
                if is_admin == 0:
                    stock_picking_batch_domain += [('user_id', '=', user_id.id)]
                if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                    stock_picking_batch_domain += filter_by_last_sync_time('stock.picking.batch', payload_data)
                stock_picking_batch_objs = stock_picking_batch.sudo().search(stock_picking_batch_domain)

            if stock_picking_batch_objs:
                if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                    stock_picking_batch_domain += filter_by_last_sync_time('stock.picking.batch', payload_data)
                stock_picking_batch_objs = stock_picking_batch_objs.search(stock_picking_batch_domain)

                response_data_list = self.get_batch_detail_response_data(self, stock_picking_batch_objs, response_data)
                return valid_response(response_data_list)
            else:
                return invalid_response('not_found', 'No Batch Picking record found.')
        except Exception as e:
            _logger.exception("Error while getting batch picking details for payload: %s", payload)
            error_msg = 'Error while getting batch picking details.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def get_stock_lot_detail_response_data(self, domain, payload_data):

        if 'last_sync_time' in payload_data and payload_data.get('last_sync_time') or 'last_sync_timestamp' in payload_data  and payload_data.get('last_sync_timestamp'):
            domain += filter_by_last_sync_time('stock.lot', payload_data)

        stock_lot = request.env['stock.lot'].sudo().search(domain)

        if 'barcode' in payload_data and payload_data.get('barcode'):
            stock_lot_objs = stock_lot.sudo().search([('name', '=', payload_data.get('barcode'))], limit=1)            
        else:
            stock_lot_objs = stock_lot.sudo().search(domain)

        if stock_lot_objs:
            response_data = []
            for lot in stock_lot_objs:         
                response_data.append({
                    'id': str(lot.id),
                    'name': lot.name,
                    'product_id': [str(lot.product_id.id), lot.product_id.name] if lot.product_id else [],
                    'company_id': [str(lot.company_id.id), lot.company_id.name] if lot.company_id else [],
                    'location_id': [str(lot.location_id.id), lot.location_id.name] if lot.location_id else [],
                })
            return {"status": True, 'data': response_data}
        else:
            return {"status": False, 'code': "not_found", 'message': "No lot found"}


    @validate_token
    @http.route("/api/get_stock_lot_detail", type="http", auth="none", methods=["GET"], csrf=False)
    def get_stock_lot_detail(self, **payload):
        """
            Gets the barcode(name for stock.lot) of a lot from request and
            Returns lot details.
        """
        _logger.info("/api/get_lot_detail payload: %s", payload)

        try:
            payload_data = payload
            domain = []

            res = self.get_stock_lot_detail_response_data(self, domain, payload_data)

            if res.get('status'):
                return valid_response(res.get('data'))
            else:
                return invalid_response(res.get('code'), res.get('message'), 200)
        except Exception as e:
            _logger.exception("Error while getting lot details for payload: %s", payload)
            error_msg = 'Error while getting lot details.'
            return invalid_response('bad_request', error_msg, 200)

    # NOTE: for mobile app --> find default location. first index of (move_line_id.move_id.location_dest_id or move_line_id.picking_id.location_dest_id or move_line_id.location_dest_id)
    # NOTE: sort default_location.putaway_rule_ids order_by package_type_ids, product_id, category_id in reverse order and check with the rules one by one.
    # NOTE: if putaway_rule.storage_category_id is not found, putaway_rule.location_out_id is the DESTINATION.
    # NOTE: if found, search in the child locations (putaway_rule.location_out_id.child_internal_location_ids). If storage_category_id is same for any child location with putaway_rule, child location is the DESTINATION. 
    # NOTE: if no child location is found with same storage_category_id of putaway rule, default location is the DESTINATION. 

    # TODO: skipped checks --> max_weight, forecast_weight, weight, product_capacity_ids, allow_new_product, qty_by_location in /stock/models/stock_location.py/_check_can_be_used()
    # TODO: skipped checks --> package type, storage category check in /stock/models/product/strategy.py/_get_putaway_location() 
    @staticmethod
    def get_putaway_rule_response_data(self, payload_data):

        putaway_rules = request.env['stock.putaway.rule'].sudo().search([])

        if putaway_rules:
            response_data = []
            for rule in putaway_rules:
                
                packages = []
                for package_type_id in rule.package_type_ids:
                    packages.append({
                        'id': str(package_type_id.id),
                        'name': package_type_id.name,
                        'barcode': package_type_id.barcode,
                        'base_weight': str(package_type_id.base_weight),
                        'company_id': [str(package_type_id.company_id.id), package_type_id.company_id.name] if package_type_id.company_id else [],
                        'height': str(package_type_id.height),
                        'length_uom_name': package_type_id.length_uom_name,
                        'max_weight': str(package_type_id.max_weight),
                        'packaging_length': str(package_type_id.packaging_length),
                        # 'storage_category_capacity_ids': # skipped for now as no necessary to calculate source & destination field
                        'weight_uom_name': package_type_id.weight_uom_name,
                        'width': str(package_type_id.width)
                    })

                response_data.append({
                    'id': str(rule.id),
                    'display_name': rule.display_name,
                    'category_id': [str(rule.category_id.id), rule.category_id.name] if rule.category_id else [],
                    'company_id': [str(rule.company_id.id), rule.company_id.name] if rule.company_id else [],
                    'location_in_id': [str(rule.location_in_id.id), rule.location_in_id.name] if rule.location_in_id else [],
                    'location_out_id': [str(rule.location_out_id.id), rule.location_out_id.name] if rule.location_out_id else [],
                    'package_type_ids': packages,
                    'product_id': [str(rule.product_id.id), rule.product_id.name] if rule.product_id else [],
                    'storage_category_id': [str(rule.storage_category_id.id), rule.storage_category_id.name] if rule.storage_category_id else []
                })
            return {"status": True, 'data': response_data}
        else:
            return {"status": False, 'code': "not_found", 'message': "No lot found"}

    @validate_token
    @http.route("/api/get_putaway_rule", type="http", auth="none", methods=["GET"], csrf=False)
    def get_putaway_rule(self, **payload):
        """
            Gets putaway rules(stock.putaway.rule) of a lot from request and
            Returns putaway rule details.
        """
        _logger.info("/api/get_putaway_rules payload: %s", payload)

        try:
            payload_data = payload

            res = self.get_putaway_rule_response_data(self, payload_data)

            if res.get('status'):
                return valid_response(res.get('data'))
            else:
                return invalid_response(res.get('code'), res.get('message'), 200)
        except Exception as e:
            _logger.exception("Error while getting putaway rules for payload: %s", payload)
            error_msg = 'Error while getting putaway rules.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def get_location_detail_response_data(stock_location_objs):

        response_data = []
        for location in stock_location_objs:
            current_stock = []
            if not ast.literal_eval(request.env['ir.config_parameter'].sudo().get_param('bista_wms_api.restrict_stock_quants_in_location', 'False')):
                stock_quants = request.env['stock.quant'].search([
                    ('location_id', 'child_of', location.id)
                ])
                if stock_quants:
                    for quant_id in stock_quants:
                        current_stock.append({
                            'id': quant_id.id,
                            'product_id': quant_id.product_id.id,
                            'product': quant_id.product_id.name,
                            'product_code': quant_id.product_id.default_code or "",
                            'barcode': quant_id.product_id.barcode or "",
                            'location': quant_id.location_id.complete_name,
                            'lot_serial': quant_id.lot_id.name if quant_id.lot_id else "",
                            'on_hand_quantity': quant_id.quantity,
                        })
            response_data.append({
                'id': location.id,
                'location_name': location.name,
                'parent_location': location.location_id.complete_name or "",
                'location_type': location.usage,
                'company': location.company_id.name,
                'company_id': [str(location.company_id.id), location.company_id.name],
                'warehouse_id': [str(location.warehouse_id.id), location.warehouse_id.name],
                'barcode': location.barcode or "",
                'storage_category': location.storage_category_id.name or "",
                'is_scrap_location': location.scrap_location,
                # NOTE: 'return_location' not exist in stock.location model from odoo18
                # 'is_return_location': location.return_location,
                'inventory_frequency': location.cyclic_inventory_frequency or 0,
                'last_inventory_date': location.last_inventory_date or "",
                'next_inventory_date': location.next_inventory_date or "",
                'removal_strategy': location.removal_strategy_id.name or "",
                'comment': location.comment or "",
                'current_stock': current_stock,
            })
        return response_data

    @validate_token
    @http.route("/api/get_location_detail", type="http", auth="none", methods=["GET"], csrf=False)
    def get_location_detail(self, **payload):
        """
            Gets the barcode of a location from request and
            returns that specific location's details.
        """
        _logger.info("/api/get_location_detail payload: %s", payload)

        try:
            payload_data = payload
            domain = []

            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                domain += filter_by_last_sync_time('stock.location', payload_data)

            stock_location = request.env['stock.location'].search(domain)

            if 'barcode' in payload_data and payload_data['barcode']:
                # get stock.location object search by barcode
                stock_location_objs = stock_location.sudo().search([
                    ('barcode', '=', payload_data.get('barcode'))], limit=1)
            else:
                domain.append(('usage', 'in', ['internal']))
                #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                # domain.append(('company_id', '=', request.env.user.company_id.id))
                stock_location_objs = stock_location.sudo().search(domain)

            if stock_location_objs:
                response_data = self.get_location_detail_response_data(stock_location_objs)
                return valid_response(response_data)
            else:
                return invalid_response('not_found', 'No location found.')
        except Exception as e:
            _logger.exception("Error while getting location details for payload: %s", payload)
            error_msg = 'Error while getting location details.'
            return invalid_response('bad_request', error_msg, 200)

    # NOTE: transfered to bista_wms_api_purchase_extension
    # @staticmethod
    # def _generate_prod_wise_purchase_report(self, prod_id):
    #     try:
    #         response_data = []

    #         date_today = datetime.now().strftime(DEFAULT_SERVER_DATE_FORMAT)

    #         parameters = {
    #             "domain": [
    #                 "&",
    #                 "&",
    #                 [
    #                     "state",
    #                     "in",
    #                     [
    #                         "purchase",
    #                         "done"
    #                     ]
    #                 ],
    #                 [
    #                     "product_tmpl_id",
    #                     "in",
    #                     [
    #                         prod_id
    #                     ]
    #                 ],
    #                 [
    #                     "date_approve",
    #                     ">=",
    #                     date_today
    #                 ]
    #             ],
    #             "groupby": [
    #                 "date_approve:day"
    #             ],
    #             "fields": [
    #                 "__count",
    #                 "qty_ordered:sum"
    #             ],
    #             "context": {
    #                 "lang": "en_US",
    #                 "tz": "Asia/Dhaka",
    #                 "uid": 2,
    #                 "allowed_company_ids": [
    #                     1
    #                 ],
    #                 "fill_temporal": True,
    #                 "active_model": "product.template",
    #                 "active_id": prod_id,
    #                 "active_ids": [
    #                     prod_id
    #                 ],
    #                 "graph_measure": "qty_ordered"
    #             },
    #             "lazy": False
    #         }
    #         response_data = request.env['purchase.report'].with_context(parameters['context']).sudo().web_read_group(
    #             domain=parameters['domain'], groupby=parameters['groupby'],
    #             fields=parameters['fields'], lazy=parameters['lazy'])
    #         for data in response_data['groups']:
    #             if data.get('__domain', False):
    #                 data.pop('__domain', None)
    #             if data.get('__range', False):
    #                 data.pop('__range', None)
    #             if not data['qty_ordered']:
    #                 data['qty_ordered'] = 0

    #         read_group_params = {
    #             "domain": [
    #                 "&",
    #                 "&",
    #                 [
    #                     "state",
    #                     "in",
    #                     [
    #                         "purchase",
    #                         "done"
    #                     ]
    #                 ],
    #                 [
    #                     "product_tmpl_id",
    #                     "in",
    #                     [
    #                         prod_id
    #                     ]
    #                 ],
    #                 [
    #                     "date_approve",
    #                     ">=",
    #                     "2021-07-29"
    #                 ]
    #             ],
    #             "groupby": [],
    #             "fields": [
    #                 "__count",
    #                 "order_id:count_distinct",
    #                 "untaxed_total:sum",
    #                 "price_total:sum",
    #                 "price_subtotal_confirmed_orders:sum(price_total)",
    #                 "price_subtotal_all_orders:sum(untaxed_total)",
    #                 "purchase_orders:count_distinct(order_id)",
    #                 # NOTE: avg_receipt_delay and avg_days_to_purchase not available in v17
    #                 # "avg_receipt_delay:avg(avg_receipt_delay)", 
    #                 # "avg_days_to_purchase:avg(avg_days_to_purchase)"
    #             ],
    #             "context": {
    #                 "lang": "en_US",
    #                 "tz": "Asia/Dhaka",
    #                 "uid": 2,
    #                 "allowed_company_ids": [
    #                     1
    #                 ],
    #                 "active_model": "product.template",
    #                 "active_id": prod_id,
    #                 "active_ids": [
    #                     prod_id
    #                 ],
    #                 "graph_measure": "qty_ordered"
    #             },
    #             "lazy": False
    #         }
    #         read_group_res_data = request.env['purchase.report'].with_context(
    #             read_group_params['context']).sudo().read_group(
    #             domain=read_group_params['domain'], groupby=read_group_params['groupby'],
    #             fields=read_group_params['fields'], lazy=read_group_params['lazy'])
    #         for elem in read_group_res_data:
    #             for key in elem:
    #                 if not elem[key]:
    #                     elem[key] = 0
    #             elem.update({
    #                 'avg_receipt_delay': 0,
    #                 'avg_days_to_purchase':0
    #             })
    #         response_data['total_count'] = read_group_res_data

    #         return valid_response(response_data)
    #     except Exception as e:
    #         _logger.exception("Error while generating purchase report for prod_id: %s", prod_id)
    #         return invalid_response('bad_request', 'Error while generating purchase report.', 200)

    # @validate_token
    # @http.route("/api/get_purchase_report", type="http", auth="none", methods=["GET"], csrf=False)
    # def get_purchase_report(self, **payload):
    #     """
    #         Gets the name of a stock_picking_batch record from request and
    #         returns that specific stock_picking_batch record's details.
    #         If name of a stock_picking_batch not in request then returns
    #         all the stock_picking_batch record details of ready state.
    #     """

    #     _logger.info("/api/get_purchase_report payload: %s", payload)
    #     payload_data = payload

    #     if 'product_tmpl_id' in payload_data:
    #         return self._generate_prod_wise_purchase_report(self, prod_id=int(payload_data['product_tmpl_id']))
    #     else:
    #         product_template_obj = request.env['product.template'].search([])

    @validate_token
    @http.route("/api/sync_barcode_data", type="http", auth="none", methods=["GET"], csrf=False)
    def sync_barcode_data(self, **payload):
        """
            Returns product, picking, batch/wave, location barcode and route.
        """

        _logger.info("/api/sync_barcode_data GET payload: %s", payload)
        try:
            response_data = []
            user_id, is_admin = self._get_user_stock_group(self)
            warehouse_id = user_id.warehouse_id

            # NOTE: We don't require barcode field from product.template model.
            # `barcode` field from product.template model automatically propagated to product.product if variant count < 1.
            # If variant count > 1, barcode field is hidden in product.template view.

            # Product Variant (product.product) barcode

            payload_data = payload
            product_product_domain = []
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                product_product_domain += filter_by_last_sync_time('product.product', payload_data)

            # product_product_objs = request.env['product.product'].search(
                # [('active', '=', True), ('barcode', '!=', False)])
            product_product_domain += [('active', '=', True), ('barcode', '!=', False)]
            product_product_objs = request.env['product.product'].sudo().search(product_product_domain)

            if product_product_objs:
                for product in product_product_objs:
                    response_data.append({
                        "barcode": product.barcode,
                        "route": "product"
                    })

            # Transfer (stock.picking) barcode
            #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
            # stock_picking_domain = [('state', '=', 'assigned'), ('company_id', '=', request.env.user.company_id.id)]
            stock_picking_domain = [('state', '=', 'assigned')]
            if is_admin == 0:
                stock_picking_domain = stock_picking_domain + [('user_id', '=', user_id.id)]

            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                stock_picking_domain += filter_by_last_sync_time('stock.picking', payload_data)
            
            stock_picking_objs = request.env['stock.picking'].search(stock_picking_domain)
            if stock_picking_objs:
                for picking in stock_picking_objs:
                    response_data.append({
                        "barcode": picking.name,
                        "route": "picking"
                    })

            # Batch Transfer (stock.picking.batch) barcode
            #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
            # stock_picking_batch_domain = [('state', '=', 'in_progress'),
            #                               ('company_id', '=', request.env.user.company_id.id)]
            stock_picking_batch_domain = [('state', '=', 'in_progress')]
            if is_admin == 0:
                stock_picking_batch_domain = stock_picking_batch_domain + [('user_id', '=', user_id.id)]
            
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                stock_picking_batch_domain += filter_by_last_sync_time('stock.picking.batch', payload_data)
            
            stock_picking_batch_objs = request.env['stock.picking.batch'].search(stock_picking_batch_domain)
            if stock_picking_batch_objs:
                for batch in stock_picking_batch_objs:
                    response_data.append({
                        "barcode": batch.name,
                        "route": "batch_wave"
                    })

            # Location (stock.location) barcode
            #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
            # stock_location_objs = request.env['stock.location'].sudo().search(
            #     [('usage', 'in', ['internal']), ('barcode', '!=', False),
            #      ('company_id', '=', request.env.user.company_id.id)])

            stock_location_domain = []
            if is_admin == 0:
                stock_location_domain += self._prepare_inventory_warehouse_domain([('warehouse_id', '=', warehouse_id.id)])

            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                stock_location_domain += filter_by_last_sync_time('stock.location', payload_data)
            stock_location_domain += [('usage', 'in', ['internal']), ('barcode', '!=', False)]

            stock_location_objs = request.env['stock.location'].sudo().search(stock_location_domain)
            if stock_location_objs:
                for location in stock_location_objs:
                    response_data.append({
                        "barcode": location.barcode,
                        "route": "location"
                    })

            # Stock package type (stock.package.type) barcode 
            stock_package_type_domain = []

            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                stock_package_type_domain += filter_by_last_sync_time('stock.package.type', payload_data)
            
            product_package_type_objs = request.env['stock.package.type'].sudo().search(stock_package_type_domain)
            if product_package_type_objs:
                for package_type in product_package_type_objs:
                    if package_type.barcode:
                        response_data.append({
                            "barcode": package_type.barcode,
                            "route": "product_package_type"
                        })

            # Product packaging (product.packaging) barcode
            product_packaging_domain = []

            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                product_packaging_domain += filter_by_last_sync_time('product.packaging', payload_data)
            
            product_packaging_objs = request.env['product.packaging'].sudo().search(product_packaging_domain)
            if product_packaging_objs:
                for packaging in product_packaging_objs:
                    if packaging.barcode:
                        response_data.append({
                            "barcode": packaging.barcode,
                            "route": "product_packaging"
                        })

            # Product packages (stock.quant.package) barcode
            product_packages_domain = [('location_id.usage', '!=', 'customer')]
            if is_admin == 0:
                product_packages_domain = product_packages_domain + \
                                          [('location_id.warehouse_id', '=', warehouse_id.id)]
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                product_packages_domain += filter_by_last_sync_time('stock.quant.package', payload_data)
            
            product_packages_objs = request.env['stock.quant.package'].sudo().search(
                product_packages_domain)
            if product_packages_objs:
                for package in product_packages_objs:
                    if package.name:
                        response_data.append({
                            "barcode": package.name,
                            "route": "product_packages"
                        })

            # Lot/Serial (stock.lot) barcode
            stock_lot_domain = []
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                stock_lot_domain += filter_by_last_sync_time('stock.lot', payload_data)
            
            stock_lot_objs = request.env['stock.lot'].sudo().search(stock_lot_domain)
            if stock_lot_objs:
                for lot_id in stock_lot_objs:
                    if lot_id.name:
                        response_data.append({
                            "barcode": lot_id.name,
                            "route": "lot_serial"
                        })

            if response_data:
                return valid_response(response_data)
            else:
                return invalid_response('not_found', 'No Data Found.')

        except Exception as e:
            _logger.exception("Error while syncing barcode data")
            error_msg = 'Error while syncing barcode data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _get_product_package_type(self, payload_data):

        response_data = []
        package_carrier_value = str()
        package_carrier_key = str()
        product_package_type = request.env['stock.package.type']
        product_package_type_objs = False

        if 'id' in payload_data or 'barcode' in payload_data:
            if 'id' in payload_data:
                if payload_data['id']:
                    product_package_type_objs = product_package_type.sudo().search(
                        [('id', '=', payload_data.get('id'))], limit=1)
            elif 'barcode' in payload_data:
                if payload_data['barcode']:
                    product_package_type_objs = product_package_type.sudo().search(
                        [('barcode', '=', payload_data.get('barcode'))], limit=1)
        else:
            domain = []
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                domain += filter_by_last_sync_time('stock.package.type', payload_data)
            product_package_type_objs = product_package_type.sudo().search(domain)

        if product_package_type_objs:
            for package_type in product_package_type_objs:
                storage_category_capacity = []
                for category_capacity in package_type.storage_category_capacity_ids:
                    storage_category_capacity.append(
                        {
                            'storage_category_id': [str(category_capacity.storage_category_id.id),
                                                    category_capacity.storage_category_id.name] if category_capacity.storage_category_id else [],
                            'product_id': [str(category_capacity.product_id.id),
                                           category_capacity.product_id.display_name] if category_capacity.product_id else [],
                            'package_type_id': [str(category_capacity.package_type_id.id),
                                                category_capacity.package_type_id.name] if category_capacity.package_type_id else [],
                            'product_uom_id': [str(category_capacity.product_uom_id.id),
                                               category_capacity.product_uom_id.name] if category_capacity.product_uom_id else [],
                            'quantity': category_capacity.quantity or "",
                        })
                if 'package_carrier_type' in package_type._fields:
                    package_carrier_value = dict(package_type._fields['package_carrier_type'].selection).get(
                        package_type.package_carrier_type)
                    package_carrier_key = package_type.package_carrier_type
                response_data.append(
                    {
                        'id': package_type.id,
                        'barcode': package_type.barcode or "",
                        'name': package_type.name,
                        'display_name': package_type.display_name,
                        'packaging_length': package_type.packaging_length,
                        'width': package_type.width,
                        'height': package_type.height,
                        'length_uom_name': package_type.length_uom_name or "",
                        'base_weight': package_type.base_weight,
                        'max_weight': package_type.max_weight,
                        'weight_uom_name': package_type.weight_uom_name or "",
                        'package_carrier_type': [package_carrier_key,
                                                 package_carrier_value] if package_carrier_value else "",
                        'shipper_package_code': package_type.shipper_package_code or "" if 'shipper_package_code' in package_type._fields else "",
                        'sequence': package_type.sequence,
                        'company_id': [str(package_type.company_id.id),
                                       package_type.company_id.name] if package_type.company_id else [],
                        'storage_category_capacity_ids': storage_category_capacity,
                        'create_uid': [str(package_type.create_uid.id),
                                       package_type.create_uid.name] if package_type.create_uid else [],
                        'create_date': package_type.create_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                        'write_uid': [str(package_type.write_uid.id),
                                      package_type.write_uid.name] if package_type.write_uid else [],
                        'write_date': package_type.write_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    })
            return response_data
        else:
            return {"status": False, "response": 'not_found', "message": 'No product package type found.'}

    @validate_token
    @http.route("/api/get_product_package_type", type="http", auth="none", methods=["GET"], csrf=False)
    def get_product_package_type(self, **payload):
        """
            Returns product_package_type info.
        """

        _logger.info("/api/get_product_package_type GET payload: %s", payload)
        try:
            payload_data = payload
            packages_enabled = request.env.user.has_group('stock.group_tracking_lot')
            if packages_enabled:
                response_data = self._get_product_package_type(self, payload_data)
                if isinstance(response_data, list):
                    return valid_response(response_data)
                elif isinstance(response_data, dict):
                    if not response_data['status']:
                        return invalid_response(response_data['response'], response_data['message'])
            else:
                return invalid_response('not_enabled', 'Package is not enabled in settings.')

        except Exception as e:
            _logger.exception("Error while getting product package type data")
            error_msg = 'Error while getting product package type data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _get_product_packages(self, stock_quant_package_objs):
        response_data = []
        stock_picking = request.env['stock.picking']
        if stock_quant_package_objs:
            for package in stock_quant_package_objs:
                package_content = []
                stock_picking_data = []
                transfer_values = package.action_view_picking()
                stock_picking_objs = stock_picking.sudo().search(transfer_values['domain'], order='id')
                for stock_picking in stock_picking_objs:
                    stock_picking_data.append(
                        {
                            'id': stock_picking.id,
                            'name': stock_picking.name
                        })
                for quant in package.quant_ids:
                    package_content.append(
                        {
                            'product_id': [str(quant.product_id.id),
                                           quant.product_id.display_name] if quant.product_id else [],
                            'lot_id': [str(quant.lot_id.id),
                                       quant.lot_id.name] if quant.lot_id else [],
                            'product_uom_id': [str(quant.product_uom_id.id),
                                               quant.product_uom_id.name] if quant.product_uom_id else [],
                            'quantity': quant.quantity or "",
                        })
                package_use_key = package.package_use
                package_use_value = dict(package._fields['package_use'].selection).get(package.package_use)
                response_data.append(
                    {
                        'id': package.id,
                        'name': package.name,
                        'display_name': package.display_name,
                        'corresponding_transfer': stock_picking_data,
                        'package_type_id': [str(package.package_type_id.id),
                                            package.package_type_id.name] if package.package_type_id else [],
                        'pack_date': package.pack_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                        'company_id': [str(package.company_id.id),
                                       package.company_id.name] if package.company_id else [],
                        'owner_id': [str(package.owner_id.id),
                                     package.owner_id.name] if package.owner_id else [],
                        'location_id': [str(package.location_id.id),
                                        package.location_id.complete_name] if package.location_id else [],
                        'warehouse_id': [str(package.location_id.warehouse_id.id),
                                         package.location_id.warehouse_id.name] if package.location_id.warehouse_id else [],
                        'package_use': [package_use_key, package_use_value] if package_use_value else "",
                        'shipping_weight': package.shipping_weight if 'shipping_weight' in package._fields else "",
                        'valid_sscc': package.valid_sscc,
                        # NOTE: transferred to bista_wms_sales_extension
                        # 'weight': round(package.weight, 2) if package.weight else package.weight,
                        # 'weight_is_kg': package.weight_is_kg,
                        # 'weight_uom_name': package.weight_uom_name or "",
                        # 'weight_uom_rounding': package.weight_uom_rounding,
                        'quant_ids': package_content,
                        'create_uid': [str(package.create_uid.id),
                                       package.create_uid.name] if package.create_uid else [],
                        'create_date': package.create_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                        'write_uid': [str(package.write_uid.id),
                                      package.write_uid.name] if package.write_uid else [],
                        'write_date': package.write_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    })
            return response_data
        else:
            return {"status": False, "response": 'not_found', "message": 'No product package type found.'}

    @validate_token
    @http.route("/api/get_product_packages", type="http", auth="none", methods=["GET"], csrf=False)
    def get_product_packages(self, **payload):
        """
            Returns product_package_type info.
        """

        _logger.info("/api/get_product_packages GET payload: %s", payload)
        try:
            payload_data = payload
            packages_enabled = request.env.user.has_group('stock.group_tracking_lot')
            user_id, is_admin = self._get_user_stock_group(self)
            stock_quant_package = request.env['stock.quant.package']
            warehouse_id = user_id.warehouse_id
            stock_quant_package_objs = False
            if packages_enabled:
                if 'id' in payload_data or 'package' in payload_data:
                    if 'id' in payload_data:
                        if payload_data['id']:
                            stock_quant_packages_domain = [('id', '=', int(payload_data['id']))]
                            if is_admin == 0:
                                stock_quant_packages_domain = stock_quant_packages_domain + [
                                    ('location_id.warehouse_id', '=', warehouse_id.id)]
                            stock_quant_package_objs = stock_quant_package.sudo().search(stock_quant_packages_domain, limit=1)
                    elif 'package' in payload_data:
                        if payload_data['package']:
                            stock_quant_packages_domain = [('name', '=', payload_data.get('package'))]
                            if is_admin == 0:
                                stock_quant_packages_domain = stock_quant_packages_domain + [
                                    ('location_id.warehouse_id', '=', warehouse_id.id)]
                            stock_quant_package_objs = stock_quant_package.sudo().search(stock_quant_packages_domain, limit=1)
                else:
                    stock_quant_packages_domain = []
                    if is_admin == 0:
                        stock_quant_packages_domain.append(('location_id.warehouse_id.id', '=', warehouse_id.id))
                    if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                        stock_quant_packages_domain += filter_by_last_sync_time('stock.quant.package', payload_data)
                    stock_quant_package_objs = stock_quant_package.sudo().search(stock_quant_packages_domain)
                response_data = self._get_product_packages(self, stock_quant_package_objs)
                if isinstance(response_data, list):
                    return valid_response(response_data)
                elif isinstance(response_data, dict):
                    if not response_data['status']:
                        return invalid_response(response_data['response'], response_data['message'])
            else:
                return invalid_response('not_enabled', 'Package is not enabled in settings.')

        except Exception as e:
            _logger.exception("Error while getting product package data")
            error_msg = 'Error while getting product package data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _get_package_sequence(self, payload_data):

        response_data = []
        number_next_actual = str()
        package_sequence_objs = False
        sequences = request.env['ir.sequence']
        stock_quant_package_obj = request.env['stock.quant.package']

        if 'id' in payload_data or 'sequence_code' in payload_data:
            if 'id' in payload_data:
                if payload_data['id']:
                    package_sequence_domain = [
                        ('id', '=', int(payload_data['id']))]
                    package_sequence_objs = sequences.sudo().search(package_sequence_domain, limit=1)
                elif 'sequence_code' in payload_data:
                    if payload_data['sequence_code']:
                        package_sequence_domain = [
                            ('code', '=', int(payload_data['sequence_code']))]
                        package_sequence_objs = sequences.sudo().search(package_sequence_domain, limit=1)
        else:
            package_sequence_domain = [('name', '=', 'Packages')]
            if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                package_sequence_domain += filter_by_last_sync_time('ir.sequence', payload_data)
            package_sequence_objs = sequences.sudo().search(package_sequence_domain)

        if package_sequence_objs:
            for sequence in package_sequence_objs:
                # stock_quant_package = stock_quant_package_obj.search(
                #     [('name', 'ilike', sequence.prefix)], order='id desc', limit=1)
                # if stock_quant_package:
                #     print('ok-------------',stock_quant_package.name,sequence.prefix)
                #     number_next_actual = int(
                #         ''.join(filter(str.isdigit, stock_quant_package.name)))
                implementation_key = sequence.implementation
                implementation_value = dict(
                    sequence._fields['implementation'].selection).get(sequence.implementation)
                response_data.append({
                    'name': sequence.name,
                    'code': sequence.code or "",
                    'active': sequence.active,
                    'implementation': [implementation_key, implementation_value] if implementation_value else "",
                    'prefix': sequence.prefix or "",
                    'suffix': sequence.suffix or "",
                    'sequence_size': sequence.padding,
                    'number_increment': sequence.number_increment,
                    'number_next': sequence.number_next,
                    'number_next_actual': sequence.number_next_actual,
                    'is_mobile_app': sequence.is_mobile_app
                })

            return response_data
        return {"status": False, "response": 'not_found', "message": 'No package sequence found.'}

    @validate_token
    @http.route("/api/get_package_sequence", type="http", auth="none", methods=["GET"], csrf=False)
    def get_package_sequence(self, **payload):
        """
            Returns package sequence info.
        """

        _logger.info("/api/get_package_sequence GET payload: %s", payload)
        try:
            payload_data = payload
            packages_enabled = request.env.user.has_group('stock.group_tracking_lot')
            if packages_enabled:
                response_data = self._get_package_sequence(self, payload_data)
                if isinstance(response_data, list):
                    return valid_response(response_data)
                elif isinstance(response_data, dict):
                    if not response_data['status']:
                        return invalid_response(response_data['response'], response_data['message'])
            else:
                return invalid_response('not_enabled', 'Package is not enabled in settings.')

        except Exception as e:
            _logger.exception("Error while getting package sequence data")
            error_msg = 'Error while getting package sequence data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def get_packaging_type_detail_response_data(self, payload_data):

        response_data = []
        product_packaging = request.env['product.packaging']
        product_packaging_objs = False

        if 'barcode' in payload_data:
            if payload_data['barcode']:
                product_packaging_domain = [('barcode', '=', payload_data.get('barcode'))]
                product_packaging_objs = product_packaging.sudo().search(product_packaging_domain, limit=1)
        elif 'name' in payload_data:
            if payload_data['name']:
                product_packaging_domain = [('name', '=', payload_data.get('name'))]
                product_packaging_objs = product_packaging.sudo().search(product_packaging_domain, limit=1)
        elif 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                product_packaging_domain = filter_by_last_sync_time('product.packaging', payload_data)
                product_packaging_objs = product_packaging.sudo().search(product_packaging_domain, limit=1)
        else:
            product_packaging_objs = product_packaging.sudo().search([])
        if product_packaging_objs:
            for product_package in product_packaging_objs:
                response_data.append({
                    'id': str(product_package.id),
                    'name': product_package.name,
                    'barcode': product_package.barcode or "",
                    'company_id': [str(product_package.company_id.id),
                                   product_package.company_id.name] if product_package.company_id else [],
                    'display_name': product_package.display_name,
                    'package_type_id': [str(product_package.package_type_id.id),
                                        product_package.package_type_id.name] if product_package.package_type_id else [],
                    'product_id': [str(product_package.product_id.id),
                                   product_package.product_id.name] if product_package.product_id else [],
                    'product_uom_id': [str(product_package.product_uom_id.id),
                                       product_package.product_uom_id.name] if product_package.product_uom_id else [],
                    # NOTE: transfered to bista_wms_api_purchase_extension
                    # 'purchase': product_package.purchase,
                    'qty': str(product_package.qty or ""),
                    'route_ids': [str(product_package.route_ids.id),
                                  product_package.route_ids.name] if product_package.route_ids else [],
                    # NOTE: transferred to bista_wms_sales_extensions
                    # 'sales': product_package.sales,
                    'sequence': str(product_package.sequence or ""),
                    'create_date': product_package.create_date,
                    'create_uid': [str(product_package.create_uid.id),
                                   product_package.create_uid.name] if product_package.create_uid else [],
                    'write_date': product_package.write_date,
                    'write_uid ': [str(product_package.write_uid.id),
                                   product_package.write_uid.name] if product_package.write_uid else [],
                })
            return response_data
        else:
            return {"status": False, "response": 'not_found', "message": 'No packaging details found.'}

    @validate_token
    @http.route("/api/get_packaging_type_detail", type="http", auth="none", methods=["GET"], csrf=False)
    def get_packaging_type_detail(self, **payload):
        """
            Gets name or barcode from the request and return packaging type information.
        """
        _logger.info("/api/get_packaging_detail payload: %s", payload)
        response_data = []
        payload_data = payload
        user_id, is_admin = self._get_user_stock_group(self)
        packaging_enabled = user_id.has_group('product.group_stock_packaging')
        try:
            if packaging_enabled:
                response_data = self.get_packaging_type_detail_response_data(self, payload_data)
                if isinstance(response_data, list):
                    return valid_response(response_data)
                elif isinstance(response_data, dict):
                    if not response_data['status']:
                        return invalid_response(response_data['response'], response_data['message'])
            else:
                error_msg = 'Product Packaging is not enabled in settings.'
                return invalid_response("not_enabled", error_msg, 200)
        except Exception as e:
            _logger.exception("Error while processing response data")
            error_msg = 'Error while generating packaging type data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _get_stock_quants(self, payload_data):
        
        """  
            Get stock quants data according to different domain value
        """
        response_data = []
        stock_quant_domain = []
        stock_quant_objs = False
        stock_quant = request.env['stock.quant']
        user_id, is_admin = self._get_user_stock_group(self)
        warehouse_id = user_id.warehouse_id

        # Here last_sync_time param is added with all other domains and will be applied for all below conditions.
        # Added to first position
        if 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
            stock_quant_domain = filter_by_last_sync_time('stock.quant', payload_data)

        stock_quant_domain += [
            ('location_id.usage', 'in', ['internal', 'transit']),
            ('location_id.location_adjustment', '=', True)
        ]

        if 'location_barcode' in payload_data or 'product_id' in payload_data or \
                'package_name' in payload_data or 'lot_serial_number' in payload_data or \
                'location' in payload_data or 'variant' in payload_data or \
                'package' in payload_data or 'lot' in payload_data or 'product' in payload_data or \
                'default_code' in payload_data:
            if 'location_barcode' in payload_data:
                if payload_data['location_barcode']:
                    stock_quant_domain = stock_quant_domain + \
                        [('location_id.barcode', '=', payload_data['location_barcode'])]
            if 'product_id' in payload_data or 'variant' in payload_data or 'default_code' in payload_data:
                if payload_data.get('product_id'):
                    stock_quant_domain = stock_quant_domain + \
                        [('product_id', '=', int(payload_data['product_id']))]
                elif payload_data.get('variant'):
                    stock_quant_domain = stock_quant_domain + \
                        [('product_id', '=', int(payload_data.get('variant')))]
                elif payload_data.get('default_code'):
                    stock_quant_domain = stock_quant_domain + \
                        [('product_id', '=', int(payload_data.get('default_code')))]
            if 'package_name' in payload_data:
                if payload_data['package_name']:
                    stock_quant_domain = stock_quant_domain + \
                        [('package_id.name', '=', payload_data['package_name'])]
            if 'lot_serial_number' in payload_data:
                if payload_data['lot_serial_number']:
                    stock_quant_domain = stock_quant_domain + \
                        [('lot_id.name', '=', payload_data['lot_serial_number'])]
            if payload_data.get('product'):
                stock_quant_domain = stock_quant_domain + \
                    [('product_id.product_tmpl_id', '=', int(payload_data.get('product')))]
            if payload_data.get('location'):
                stock_quant_domain = stock_quant_domain + \
                    [('location_id', '=', int(payload_data.get('location')))]
            if payload_data.get('package'):
                stock_quant_domain = stock_quant_domain + \
                    [('package_id', '=', int(payload_data.get('package')))]
            if payload_data.get('lot'):
                stock_quant_domain = stock_quant_domain + \
                    [('lot_id', '=', int(payload_data.get('lot')))]

            if is_admin == 0:
                # NOTE: shifted warehouse domain in _prepare_inventory_warehouse_domain function to inherit and modify
                # stock_quant_domain = stock_quant_domain + \
                #     [('warehouse_id', '=', warehouse_id.id)]
                stock_quant_domain += self._prepare_inventory_warehouse_domain([('warehouse_id', '=', warehouse_id.id)])
            stock_quant_objs = stock_quant.sudo().search(
                stock_quant_domain, order="location_id")
        else:
            if is_admin == 0:
                # NOTE: shifted warehouse domain in _prepare_inventory_warehouse_domain function to inherit and modify
                # stock_quant_domain = stock_quant_domain + \
                #     [('warehouse_id', '=', warehouse_id.id)]
                stock_quant_domain += self._prepare_inventory_warehouse_domain([('warehouse_id', '=', warehouse_id.id)])
            stock_quant_objs = stock_quant.sudo().search(
                stock_quant_domain, order="location_id")
        if stock_quant_objs:
            for quant_id in stock_quant_objs:
                response_data.append({
                    'id': quant_id.id,
                    'location_barcode': quant_id.location_id.barcode or "",
                    'location_adjustment': quant_id.location_id.location_adjustment,
                    'product_id': [str(quant_id.product_id.id),
                                   quant_id.product_id.display_name] if quant_id.product_id else [],
                    'lot_id': [str(quant_id.lot_id.id),
                               quant_id.lot_id.name] if quant_id.lot_id else [],
                    'package_id': [str(quant_id.package_id.id),
                                   quant_id.package_id.name] if quant_id.package_id else [],
                    'owner_id': [str(quant_id.owner_id.id),
                                 quant_id.owner_id.name] if quant_id.owner_id else [],
                    'location_id': [str(quant_id.location_id.id),
                                    quant_id.location_id.display_name] if quant_id.location_id else [],
                    'quantity': quant_id.quantity,
                    'available_quantity': quant_id.available_quantity,
                    'reserved_quantity': quant_id.reserved_quantity,
                    'product_uom_id': [str(quant_id.product_uom_id.id),
                                       quant_id.product_uom_id.name] if quant_id.product_uom_id else [],
                    'inventory_quantity': quant_id.inventory_quantity,
                    'inventory_diff_quantity': quant_id.inventory_diff_quantity,
                    'inventory_date': quant_id.inventory_date,
                    'user_id': [str(quant_id.user_id.id),
                                quant_id.user_id.name] if quant_id.user_id else [],
                    'company_id':[str(quant_id.company_id.id),
                                quant_id.company_id.name] if quant_id.company_id else [],
                })
            return response_data
        else:
            return {"status": False, "response": 'not_found', "message": 'No stock quant data found.'}

    @validate_token
    @http.route("/api/get_stock_quants", type="http", auth="none", methods=["GET"], csrf=False)
    def get_stock_quants(self, **payload):
        """
            Returns stock quant info.
        """
        _logger.info("/api/get_stock_quants GET payload: %s", payload)
        try:
            payload_data = payload
            response_data = self._get_stock_quants(self, payload_data)
            if isinstance(response_data, list):
                return valid_response(response_data)
            elif isinstance(response_data, dict):
                return invalid_response(response_data['response'], response_data['message'])
        except Exception as e:
            _logger.exception("Error while getting stock quant data")
            error_msg = 'Error while getting stock quant data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _get_res_partner(self, partner_objs, payload_data, partner_domain):
        response_data = []
        if partner_objs:
            for contact in partner_objs:
                response_data.append({
                    'id': contact.id,
                    'name': contact.name,
                    'display_name': contact.display_name,
                    'email': contact.email or "",
                    'mobile': contact.mobile or "",
                    'phone': contact.phone or "",
                    'street': contact.street or "",
                    'street2': contact.street2 or "",
                    'city': contact.city or "",
                    'vat': contact.vat or "",
                    'state_id': [str(contact.state_id.id),
                                 contact.state_id.name] if contact.state_id else [],
                    'country_id': [str(contact.country_id.id),
                                   contact.country_id.name] if contact.country_id else [],
                    'zip': contact.zip or "",
                    'company_id': [str(contact.company_id.id),
                                   contact.company_id.name] if contact.company_id else [],
                    
                    # 'property_account_payable_id': [str(contact.property_account_payable_id.id),
                    #                                 contact.property_account_payable_id.name] if contact.property_account_payable_id else [],
                    # 'property_account_receivable_id': [str(contact.property_account_receivable_id.id),
                    #                                    contact.property_account_receivable_id.name] if contact.property_account_receivable_id else []
                })
            return response_data
        else:
            return {"status": False, "response": 'not_found', "message": 'No partner data found.'}       
        
    @validate_token
    @http.route("/api/get_res_partner_info", type="http", auth="none", methods=["GET"], csrf=False)
    def get_res_partner_info(self, **payload):
        """
            Returns res partner data.
        """
        _logger.info("/api/get_res_partner_info GET payload: %s", payload)
        try:
            payload_data = payload
            response_data = []
            partner_domain = []
            partner_objs = False
            partner = request.env['res.partner']
            user_id, is_admin = self._get_user_stock_group(self)
            if 'partner_id' in payload_data:
                if payload_data['partner_id']:
                    partner_domain.append(('id','=',int(payload_data['partner_id'])))
                    partner_objs = partner.sudo().search(partner_domain, limit=1)
            elif 'last_sync_time' in payload_data and payload_data['last_sync_time'] or 'last_sync_timestamp' in payload_data  and payload_data['last_sync_timestamp']:
                partner_domain += filter_by_last_sync_time('res.partner', payload_data)
                partner_objs = partner.sudo().search(partner_domain)
            else:
                partner_objs = partner.sudo().search(partner_domain)
            response_data = self._get_res_partner(self, partner_objs, payload_data, partner_domain)
            if isinstance(response_data, list):
                return valid_response(response_data)
            elif isinstance(response_data, dict):
                return invalid_response(response_data['response'], response_data['message'])
        except Exception as e:
            _logger.exception("Error while getting res partner data", e)
            error_msg = 'Error while getting res partner data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _get_wms_config_data(self, payload_data):
        response_data = []
        domain = []
        BistaWmsConfig = request.env['bista.wms.config.settings'].sudo()
        user_id, is_admin = self._get_user_stock_group(self)

        if 'warehouse_id' or 'company_id' in payload_data:
            if 'warehouse_id' in payload_data and payload_data['warehouse_id']:
                domain += [('warehouse_id', '=', int(payload_data['warehouse_id']))]
            if 'company_id' in payload_data and payload_data['company_id']:
                domain += [('company_id', '=', int(payload_data['company_id']))]
            if is_admin == 0:    # Checking user is admin or not.0 for admin,1 for admin.
                domain += [('user_id', '=', user_id.id)]

        BistaWmsConfig = BistaWmsConfig.search(domain)  # searching in custom module for available data
        if BistaWmsConfig:
            for config_id in BistaWmsConfig:
                response_data.append({
                    'user_id': [str(config_id.user_id.id),
                                config_id.user_id.name] if config_id.user_id else [],
                    'warehouse_id': [str(config_id.warehouse_id.id),
                                     config_id.warehouse_id.name] if config_id.warehouse_id else [],
                    'company_id': [str(config_id.company_id.id),
                                   config_id.company_id.name] if config_id.company_id else [],
                    'product_packages': config_id.product_packages,
                    'product_packaging': config_id.product_packaging,
                    'wms_licensing_key': config_id.wms_licensing_key or "",
                    'batch_transfer': config_id.batch_transfer,
                    'quality': config_id.quality,
                    'barcode_scanner': config_id.barcode_scanner,
                    'barcode_gst1': config_id.barcode_gst1,
                    'delivery_method': config_id.delivery_method,
                    'lot_on_invoice': config_id.lot_on_invoice,
                    'consignment': config_id.consignment,
                    'product_variants': config_id.product_variants,
                    'units_of_measure': config_id.units_of_measure,
                    'storage_locations': config_id.storage_locations,
                    'multi_step_routes': config_id.multi_step_routes,
                    'storage_categories': config_id.storage_categories,
                    'use_qr_code': config_id.use_qr_code,
                    'use_qr_code_print_label': config_id.use_qr_code_print_label,
                    'use_qr_code_picking_operations': config_id.use_qr_code_picking_operations,
                    'use_qr_code_batch_operations': config_id.use_qr_code_batch_operations,
                    'expiration_dates': config_id.expiration_dates,
                })

            return response_data
        else:
            return {"status": False, "response": 'not_found', "message": 'No configuration data found.'}

    @validate_token
    @http.route("/api/get_wms_config_settings", type="http", auth="none", methods=["GET"], csrf=False)
    def get_wms_config_settings(self, **payload):
        """
            Returns configuration settings for users.
        """
        _logger.info("/api/get_wms_config_settings GET payload: %s", payload)
        try:

            payload_data = payload
            response = self._get_wms_config_data(self, payload_data) # calling function to get list of available data
            if isinstance(response, list):
                return valid_response(response)
            elif isinstance(response, dict):
                return invalid_response(response['response'], response['message'])
            else:
                return invalid_response('bad_request', 'Unknown Error', 200)

        except Exception as e:
            _logger.exception("Error while getting configuration settings data", e)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while getting configuration settings data'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _get_wms_settings_data(self, payload_data):
        response_data = {}
        # user_id, is_admin = self._get_user_stock_group(self)
        allowed_companies_data = []
        for company_id in request.env.user.company_ids:
            allowed_companies_data.append({
                'id': company_id.id,
                'name': str(company_id.name)
            })
        response_data.update({
            'allowed_companies': allowed_companies_data,
        })
        if response_data:
            return {"status": True, 'data': response_data}
        else:
            return {"status": False, "response": 'not_found', "message": 'No allowed company found.'}

    @validate_token
    @http.route("/api/get_wms_settings", type="http", auth="none", methods=["GET"], csrf=False)
    def get_wms_settings(self, **payload):
        """
            Returns  settings data for users.
        """
        _logger.info("/api/get_wms_settings GET payload: %s", payload)
        try:

            payload_data = payload
            response = self._get_wms_settings_data(self, payload_data)  # calling function to get list of available data
            if response.get('status'):
                return valid_response(response.get('data'))
            else:
                return invalid_response(response['response'], response['message'])
        except Exception as e:
            _logger.exception("Error while getting wms settings data", e)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while getting wms settings data'
            return invalid_response('bad_request', error_msg, 200)
    
    def _type_model_struct(self):
        type_model_dict = [
            {
                'type': 'product',
                'model': 'product.template'
            },
            {
                'type': 'variant',
                'model': 'product.product'
            },
            {
                'type': 'location',
                'model': 'stock.location'
            },
            {
                'type': 'package',
                'model': 'stock.quant.package'
            },
            {
                'type': 'lot',
                'model': 'stock.lot'
            },
            {
                'type': 'default_code',
                'model': 'product.product'
            },
        ]
        return type_model_dict
    
    def _prepare_search_domain(self, payload_data):
        """ Returns domain based on type and value"""
        domain = []
        value = payload_data['value']

        if payload_data.get('type') == 'variant' or payload_data.get('type') == 'product' or payload_data.get('type') == 'location':
            domain += ['|', ('name','ilike', value),('barcode','ilike',value)]

        if payload_data.get('type') == 'lot' or payload_data.get('type') == 'package':
            domain += [('name','ilike', value)]
        
        if payload_data.get('type') == 'default_code':
            domain += [('default_code', 'ilike', value)]

        return domain

    @staticmethod
    def _get_wms_search_data(self, payload_data):
        response_data = []
        def_search_limit = None
        def_search_limit = payload_data.get('limit')
        if not def_search_limit:
            if request.env['ir.config_parameter'].sudo().get_param('bista_wms_api.enable_search_limit'):
                def_search_limit = request.env['ir.config_parameter'].sudo().get_param('bista_wms_api.def_search_limit')

        if payload_data.get('value') and payload_data.get('type') :
            type_model_arr = self._type_model_struct()
            domain = self._prepare_search_domain(payload_data)

            for item in type_model_arr:
                if item.get('type') == payload_data.get('type'):
                    search_ids = request.env[item.get('model')].sudo().search(domain, limit=def_search_limit)
                    if search_ids:
                        for rec in search_ids:
                            response_data.append({
                                'id': rec.id,
                                'name': rec.display_name
                            })

        if response_data:
            return {'status': True, 'data': response_data}
        else:
            return {"status": False, "response": 'not_found', "message": 'No data found.'}

    @validate_token
    @http.route("/api/get_wms_search", type="http", auth="none", methods=["GET"], csrf=False)
    def get_wms_search(self, **payload):
        """
            Returns datas of searched records base on type and value.
        """
        _logger.info("/api/get_wms_search GET payload: %s", payload)
        try:

            payload_data = payload
            response = self._get_wms_search_data(self, payload_data)
            if response.get('status'):
                return valid_response(response.get('data'))
            else:
                return invalid_response(response['response'], response['message'])
        except Exception as e:
            _logger.exception("Error while getting wms search data", e)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while getting wms search data'
            return invalid_response('bad_request', error_msg, 200)


    #######################################
    # POST APIs
    #######################################
    @staticmethod
    def _stock_move_line_create_write(self, move_line, vals):
        """
        This function is written for auto pic, which is in
        bista_auto_pick_wms_api module. By default, it will return
        the dictionary of values which is passed in vals parameter
        which is a dictionary for create or write the move lines.
        when the autopic is enabled it will check the move line
        for packaging in the inherited method in the autopick module.
        """
        return vals

    @staticmethod
    def _stock_picking_create_write(self, stock_picking_obj, req_data):
        """ Update stock_picking_obj with picking attributes in post_picking_validate"""        
        return True

    @staticmethod
    def _prepare_picking_data(self, stock_picking_obj, move_line_ids, line_pack_dict):

        stock_move = request.env['stock.move']
        stock_move_line = request.env['stock.move.line']
        stock_prod_lot = request.env['stock.lot']
        pack_obj_list = []

        created_move_line_ids = []
        for move_line in move_line_ids:
            if move_line.get('id'):
                created_move_line_ids.append(move_line['id'])
        for move_line in move_line_ids:
            lot_id = False
            lot_name = False
            package_id = False
            # if not request.env.context.get('skip_line_matching'):
            if not move_line.get('id') and not move_line.get('skip_line_matching'):
                if not move_line.get('id'):  # if no move line id passes
                    #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                    # line_domain = [
                    #     ('picking_id', '=', stock_picking_obj.id),
                    #     ('id','not in',created_move_line_ids),

                    #     # comented form odoo 16
                    #     # ('reserved_uom_qty', '=', move_line.get('quantity_done')),
                    #     ('quantity', '=', move_line.get('quantity_done')),
                    #     ('product_id', '=', move_line.get('product_id')),
                    #     ('company_id', '=', request.env.user.company_id.id)
                    # ]
                    line_domain = [
                        ('picking_id', '=', stock_picking_obj.id),
                        ('id','not in',created_move_line_ids),

                        # comented form odoo 16
                        # ('reserved_uom_qty', '=', move_line.get('quantity_done')),
                        ('quantity', '=', move_line.get('quantity_done')),
                        ('product_id', '=', move_line.get('product_id')),
                    ]
                    if move_line.get('lot_id') or move_line.get('stock_lot_id'):
                        lot_domain = [('product_id', '=', move_line.get('product_id'))]
                        if move_line.get('lot_id'):
                            lot_domain.insert(0, ('name', '=', move_line.get('lot_id')))
                        elif move_line.get('stock_lot_id'):
                            lot_domain.insert(0, ('id', '=', move_line.get('stock_lot_id')))
                        line_domain.append(
                            ('lot_id', '=', stock_prod_lot.search(lot_domain, limit=1).id))
                    line_id = request.env['stock.move.line'].search(line_domain, limit=1)
                    if line_id:
                        move_line['id'] = line_id.id
            if move_line.get('skip_line_matching'):
                move_line.pop('skip_line_matching')
                
            if move_line.get('stock_lot_id'):
                # if existing lot id is given in reqeust body
                lot_id= move_line.get('stock_lot_id')

            if move_line.get('lot_id') and isinstance(move_line.get('lot_id'), str):
                #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                # lot_detail = stock_prod_lot.sudo().search([
                #     ('name', '=', move_line.get('lot_id')),
                #     ('product_id', '=', move_line.get('product_id')),
                #     ('company_id', '=', request.env.user.company_id.id)
                # ], limit=1)
                lot_detail = stock_prod_lot.sudo().search([
                    ('name', '=', move_line.get('lot_id')),
                    ('product_id', '=', move_line.get('product_id')),
                ], limit=1)

                if not lot_detail:
                    lot_detail = stock_prod_lot.create({
                        'name': move_line.get('lot_id'),
                        'product_id': move_line.get('product_id'),
                        'company_id': stock_picking_obj.company_id.id,
                    })

                if stock_picking_obj.picking_type_id.code in ['outgoing', 'internal']:
                    # for Delivery Orders and Internal transfer
                    lot_id = lot_detail.id
                    lot_name = lot_detail.name
                if stock_picking_obj.picking_type_id.code == 'incoming':  # for Receipts
                    if stock_picking_obj.picking_type_id.use_existing_lots:  # Use Existing lots enabled
                        lot_id = lot_detail.id
                    else:  # Use Create New lots enabled
                        # lot_name = move_line.get('lot_id')
                        lot_name = lot_detail.name
                        lot_id = lot_detail.id

            if move_line.get("id"):  # if move.line id exists in the system.
                move_line_obj = stock_move_line.sudo().browse(move_line.get("id"))

                # move_line_obj.reserved_uom_qty = 0
                # move_line_obj.qty_done = move_line.get('quantity_done')
                # move_line_obj.lot_id = lot_id
                # move_line_obj.lot_name = lot_name
                move_line_vals = {'quantity': move_line.get('quantity_done')}

                if lot_id or lot_name:
                    move_line_vals.update({
                        'lot_id': lot_id if lot_id else False,
                        'lot_name': lot_name,
                    })

                if move_line.get('location_id') or move_line.get('location_dest_id'):
                    # if From and To location needs to be updated while validating picking operation
                    if move_line.get('location_id') and move_line_obj.location_id.id!= move_line.get('location_id'):
                        move_line_vals.update({'location_id': move_line.get('location_id')})
                    if move_line.get('location_dest_id') and move_line_obj.location_dest_id.id != move_line.get('location_dest_id'):
                        move_line_vals.update({'location_dest_id': move_line.get('location_dest_id')})

                new_vals = self._stock_move_line_create_write(self, move_line=move_line, vals=move_line_vals)


                # ............Suprodip Sarkar................#
                prev_move_line_obj = move_line_obj._origin
                obj = app_changed_create_write(stock_picking_obj, move_line_obj, new_vals, prev_move_line_obj)
                move_line_obj.with_context(skip_custom_write=True).write(new_vals)
                # move_line_obj.write(new_vals)
                if obj:
                    stock_picking_obj.app_change_ids = [(4, obj.id)]
                # ............Suprodip Sarkar................#

                if len(move_line.get('product_package', "")) > 0:
                    line_pack_dict[move_line.get('product_package')].append(move_line.get('id'))
                    #     product_package_list.update({move_line['product_package']: package_obj.id})

                elif isinstance(move_line.get('product_packages_id'), int):
                    move_line_obj.result_package_id = move_line.get('product_packages_id')

            else:  # if move.line id does not exist, create new record.
                move_line_product = False
                move_obj = stock_move.sudo().search([
                    ('picking_id', '=', stock_picking_obj.id),
                    ('product_id', '=', move_line.get('product_id'))])
                if not move_obj:
                    move_line_product = request.env['product.product'].sudo().search(
                        [('id', '=', move_line.get('product_id')), ('company_id', '=', stock_picking_obj.company_id.id)])

                if isinstance(move_line.get('product_packages_id'), int):
                    if not move_line.get('product_package'):
                        package_id = move_line.get('product_packages_id')

                line_location_id = move_obj.location_id.id if move_obj else stock_picking_obj.location_id.id
                line_location_dest_id = move_obj.location_dest_id.id if move_obj else stock_picking_obj.location_dest_id.id

                vals = {
                    'company_id': request.env.user.company_id.id,
                    'picking_id': stock_picking_obj.id,
                    'move_id': move_obj.id if move_obj else False,
                    'product_id': move_obj.product_id.id if move_obj else move_line_product.id,
                    # 'product_uom_qty': move_line.get('quantity_done'),
                    'quantity': move_line.get('quantity_done'),
                    'product_uom_id': move_obj.product_uom.id if move_obj else move_line_product.uom_id.id,
                    'location_id': move_line.get('location_id') if move_line.get('location_id') else line_location_id,
                    'location_dest_id': move_line.get('location_dest_id') if move_line.get('location_dest_id') else line_location_dest_id,
                    'lot_id': lot_id,
                    # 'lot_name': lot_name,
                    'result_package_id': package_id,
                }
                # line_obj = stock_move_line.create(vals)
                new_vals = self._stock_move_line_create_write(self, move_line=move_line, vals=vals)

                # ............Suprodip Sarkar................#
                line_obj = stock_move_line.create(new_vals)
                # if line_obj and line_obj.move_id.product_uom_qty == 0:
                #     line_obj.move_id.write({'product_uom_qty':1})
                app_changed_create_write(stock_picking_obj, line_obj, new_vals)
                # ............Suprodip Sarkar................#
                
                if len(move_line.get('product_package', "")) > 0:
                    line_pack_dict[move_line.get('product_package')].append(line_obj.id)

        if line_pack_dict:
            for pack, move_line_ids in line_pack_dict.items():
                if move_line_ids:
                    line_to_pack_obj = stock_move_line.browse(list(set(move_line_ids)))
                    # pack_obj = stock_picking_obj._put_in_pack(line_to_pack_obj, create_package_level=True)
                    pack_obj = stock_picking_obj._put_in_pack(line_to_pack_obj)
                    if pack_obj:
                        pack_obj.name = pack
                        pack_obj_list.append(pack_obj.id)
        # if line_pack_dict and pack_obj_list:
        #     prepared_package = request.env['stock.quant.package'].browse(pack_obj_list)
        # else:
        #     prepared_package = 'No pack'
        return "", True


    @staticmethod
    def post_picking_validate_response_data(self, payload):

        package_id = False
        package_obj = False
        params = ["picking_id", "move_line_ids"]
        stock_quant_package = request.env['stock.quant.package']

        req_data = payload if len(payload) > 0 else json.loads(
            request.httprequest.data.decode())  # convert the bytes format to dict format
        req_params = {key: req_data.get(key) for key in params if req_data.get(key)}
        picking_id, move_line_ids = (
            req_params.get("picking_id"),
            req_params.get("move_line_ids")
        )
        _data_included_in_body = all([picking_id, move_line_ids])
        if not _data_included_in_body:
            # ToDo: Check if it is a batch sync, change response.
            if 'batch_validate' in req_data:
                return {'code': "post_data_error", 'message': "Data is not valid, please check again",
                        'picking_id': req_data['picking_id'], "batch_validate": True}
            return {"status": False, 'code': "post_data_error", 'message': "Data is not valid, please check again",
                    'picking_id': req_data['picking_id']}
            # return invalid_response("post_data_error", "Data is not valid, please check again", 200)
        else:
            _logger.info("Updating Stock Picking Transfers")
            stock_picking = request.env['stock.picking']
            stock_move = request.env['stock.move']
            stock_move_line = request.env['stock.move.line']
            stock_prod_lot = request.env['stock.lot']

            stock_picking_obj = stock_picking.sudo().search([('id', '=', req_params.get("picking_id"))])

            if stock_picking_obj.state == 'done':
                # ToDo: Check if it is a batch sync, change response.
                if 'batch_validate' in req_data:
                    return {'code': "already_validated", 'message': "This picking is already done.",
                            'picking_id': stock_picking_obj.id, "batch_validate": True}
                return {"status": False, 'code': "already_validated", 'message': "This picking is already done.",
                        'picking_id': stock_picking_obj.id}
                # return invalid_response("already_validated", "This picking is already done.", 200)

            # if stock_picking_obj.picking_type_id.code == 'incoming':  # for Receipts
            #     stock_picking_obj.move_line_ids.unlink()

            if move_line_ids:

                # product_package_list = {}
                line_pack_dict = defaultdict(list)
                res_str, picking_response = self._prepare_picking_data(self, stock_picking_obj, move_line_ids,
                                                                    line_pack_dict)

                # for move_line in move_line_ids:
                #     lot_id = False
                #     lot_name = False
                #     if not move_line.get('id'):
                #         line_domain = [
                #             ('picking_id', '=', picking_id),
                #             ('reserved_uom_qty', '=', move_line.get('quantity_done')),
                #             ('product_id', '=', move_line.get('product_id')),
                #             ('company_id', '=', request.env.user.company_id.id)
                #         ]
                #         if move_line.get('lot_id'):
                #             line_domain.append(
                #                 ('lot_id', '=', stock_prod_lot.search([('name', '=', move_line.get('lot_id')),
                #                                                        ('product_id', '=', move_line.get('product_id'))],
                #                                                         limit=1).id))
                #         line_id = request.env['stock.move.line'].search(line_domain, limit=1)
                #         if line_id:
                #             move_line['id'] = line_id.id
                #
                #     if move_line.get('lot_id') and isinstance(move_line.get('lot_id'),str):
                #         lot_detail = stock_prod_lot.sudo().search([
                #             ('name', '=', move_line.get('lot_id')),
                #             ('product_id', '=', move_line.get('product_id')),
                #             ('company_id', '=', request.env.user.company_id.id)
                #         ], limit=1)
                #
                #         if not lot_detail:
                #             lot_detail = stock_prod_lot.create({
                #                 'name': move_line.get('lot_id'),
                #                 'product_id': move_line.get('product_id'),
                #                 'company_id': request.env.user.company_id.id,
                #             })
                #
                #         if stock_picking_obj.picking_type_id.code in ['outgoing', 'internal']:
                #             # for Delivery Orders and Internal transfer
                #             lot_id = lot_detail.id
                #         if stock_picking_obj.picking_type_id.code == 'incoming':  # for Receipts
                #             if stock_picking_obj.picking_type_id.use_existing_lots:  # Use Existing lots enabled
                #                 lot_id = lot_detail.id
                #             else:  # Use Create New lots enabled
                #                 lot_name = move_line.get('lot_id')
                #
                #     if move_line.get("id"):  # if move.line id exists in the system.
                #         move_line_obj = stock_move_line.sudo().browse(move_line.get("id"))
                #
                #         move_line_obj.reserved_uom_qty = 0
                #         move_line_obj.qty_done = move_line.get('quantity_done')
                #         move_line_obj.lot_id = lot_id
                #         move_line_obj.lot_name = lot_name
                #
                #         if move_line.get('product_package'):
                #             line_pack_dict[move_line.get('product_package')].append(move_line.get('id'))
                #
                #             # if move_line['product_package'] in product_package_list:
                #             #     move_line_obj.result_package_id = product_package_list[move_line.get('product_package')]
                #             #
                #             # else:
                #             #     package_obj = stock_quant_package.search(
                #             #         [('name', '=', move_line.get('product_package'))], limit=1)
                #             #     if not package_obj:
                #             #         package_obj = stock_quant_package.create(
                #             #             {
                #             #                 'name': move_line.get('product_package'),
                #             #                 'package_use': 'disposable'
                #             #             })
                #             #     move_line_obj.result_package_id = package_obj.id
                #             #
                #             #     product_package_list.update({move_line['product_package']: package_obj.id})
                #
                #         elif isinstance(move_line.get('product_packages_id'), int):
                #             move_line_obj.result_package_id = move_line.get('product_packages_id')
                #
                #         # if stock_picking_obj.picking_type_id.code == 'outgoing':  # for Delivery Orders
                #         #     move_line_obj.lot_id = lot_detail[0].id
                #         # if stock_picking_obj.picking_type_id.code == 'incoming':  # for Receipts
                #         #     if stock_picking_obj.picking_type_id.use_existing_lots:  # Use Existing lots enabled
                #         #         move_line_obj.lot_id = lot_detail[0].id
                #         #     else:  # Use Create New lots enabled
                #         #         move_line_obj.lot_name = move_line.get('lot_id')
                #
                #     else:  # if move.line id does not exist, create new record.
                #         move_obj = stock_move.sudo().search([
                #             ('picking_id', '=', req_params.get("picking_id")),
                #             ('product_id', '=', move_line.get('product_id')),
                #         ])
                #
                #         # if move_line.get('product_package'):
                #         #
                #         #     if move_line['product_package'] in product_package_list:
                #         #         package_id = product_package_list[move_line.get('product_package')]
                #         #
                #         #     else:
                #         #         package_obj = stock_quant_package.search(
                #         #             [('name', '=', move_line.get('product_package'))], limit=1)
                #         #         if not package_obj:
                #         #             package_obj = stock_quant_package.create(
                #         #                 {
                #         #                     'name': move_line.get('product_package'),
                #         #                     'package_use': 'disposable'
                #         #                 })
                #         #         package_id = package_obj.id
                #         #
                #         #         product_package_list.update({move_line['product_package']: package_id})
                #
                #         if isinstance(move_line.get('product_packages_id'), int):
                #             if not move_line.get('product_package'):
                #                 package_id = move_line.get('product_packages_id')
                #
                #         vals = {
                #             'company_id': request.env.user.company_id.id,
                #             'picking_id': stock_picking_obj.id,
                #             'move_id': move_obj.id,
                #             'product_id': move_obj.product_id.id,
                #             # 'product_uom_qty': move_line.get('quantity_done'),
                #             'qty_done': move_line.get('quantity_done'),
                #             'product_uom_id': move_obj.product_uom.id,
                #             'location_id': move_obj.location_id.id,
                #             'location_dest_id': move_obj.location_dest_id.id,
                #             'lot_id': lot_id,
                #             'lot_name': lot_name,
                #             'result_package_id': package_id if package_id else False,
                #         }
                #         line_obj = request.env['stock.move.line'].create(vals)
                #         line_pack_dict[move_line.get('product_package')].append(line_obj.id)
                #
                # if line_pack_dict:
                #     for pack, line_ids in line_pack_dict.items():
                #         if line_ids:
                #             line_to_pack_obj = stock_move_line.browse(list(set(line_ids)))
                #             pack_obj = stock_picking_obj._put_in_pack(line_to_pack_obj, create_package_level=True)
                #             if pack_obj:
                #                 pack_obj.name = pack

                # stock_picking_obj.state = 'done'
                self._stock_picking_create_write(self, stock_picking_obj, req_data)
                if picking_response:
                    if 'create_backorder' in req_data and not req_data.get('create_backorder'):
                        stock_picking_obj = stock_picking_obj.with_context(picking_ids_not_to_backorder = stock_picking_obj.ids)
                    stock_picking_obj.with_context(skip_immediate=True, skip_sms=True,
                                                skip_backorder=True,
                                                # picking_ids_not_to_backorder=stock_picking_obj.ids
                                                ).button_validate()

                    # ToDo: Check if it is a batch sync, change response.
                    if 'batch_validate' in req_data:
                        return {'message': "Transfer is validated.", 'picking_id': stock_picking_obj.id,
                                "batch_validate": True}

                    return {"status": True, 'message': "Transfer is validated.", 'picking_id': stock_picking_obj.id}
                else:
                    if 'batch_validate' in req_data:
                        return {'code': "unknown error", 'message': "Error while preparing picking data",
                            'picking_id': stock_picking_obj.id, "batch_validate": True}
                    return {"status": False, 'code': "unknown error", 'message': "Error while preparing picking data",
                            'picking_id': stock_picking_obj.id}

                # return valid_response({'message': "Transfer is validated.", 'picking_id': stock_picking_obj.id})

            else:
                # ToDo: Check if it is a batch sync, change response.
                if 'batch_validate' in req_data:
                    return {'code': "move_line_ids_empty", 'message': "Move lines are empty.",
                            'picking_id': stock_picking_obj.id, "batch_validate": True}
                return {"status": False, 'code': "move_line_ids_empty", 'message': "Move lines are empty.",
                        'picking_id': stock_picking_obj.id}

                # return invalid_response("move_line_ids_empty", "Move lines are empty.", 200)
        
    @validate_token
    @http.route("/api/post_picking_validate", type="json", auth="none", methods=["POST"], csrf=False)
    def post_picking_validate(self, **payload):
        _logger.info("/api/post_picking_validate payload: %s", payload)

        try:
            res = self.post_picking_validate_response_data(self, payload)

            if isinstance(res, list):
                if any(dictionary.get('batch_validate') == True for dictionary in res):
                    return res
                else:
                    return valid_response(res)

            elif isinstance(res, dict):
                if res.get('batch_validate'):
                    return res
                if res.get('status'):
                    return valid_response(res)
                else:
                    return invalid_response(res['code'], res['message'], 200)
            else:
                return invalid_response('bad_request', 'Unknown Error', 200)

        except Exception as e:
            _logger.exception("Error while validating picking for payload: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while Validating Picking.'
            req_data = payload if len(payload) > 0 else json.loads(request.httprequest.data.decode())
            if req_data.get('batch_validate'):
                raise Exception(error_msg)
            return invalid_response('bad_request', error_msg, 200)

    @validate_token
    @http.route("/api/batch_post_picking_validate", type="json", auth="none", methods=["POST"], csrf=False)
    def batch_post_picking_validate(self, **payload):
        _logger.info("/api/batch_post_picking_validate payload: %s", payload)

        try:
            # convert the bytes format to `list of dict` format
            req_data = json.loads(request.httprequest.data.decode())
            batch_res = []
            for data in req_data['data']:
                data['batch_validate'] = True
                batch_res.append(self.post_picking_validate(**data))
            return valid_response(batch_res)
        except Exception as e:
            _logger.exception("Error while validating batch picking for payload: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while validating batch picking.'
            # return error_msg, False
            return invalid_response('bad_request', error_msg, 200)


    @validate_token
    @http.route("/api/user_detail", type="json", auth="none", methods=["POST"], csrf=False)
    def post_user_detail(self, **payload):
        _logger.info("/api/user_detail POST payload: %s", payload)

        try:
            access_token = request.httprequest.headers.get("access-token")
            user_id = request.env['api.access_token'].sudo().search([('token', '=', access_token)], limit=1).user_id
            if user_id and request.httprequest.method == 'POST':
                # convert the bytes format to `list of dict` format
                req_data = json.loads(request.httprequest.data.decode())
                if 'name' in req_data['data'].keys() or 'image' in req_data['data'].keys():
                    if 'name' in req_data['data'].keys():
                        name = req_data['data']['name']
                        if name != user_id.name:
                            user_id.name = name
                    if 'image' in req_data['data'].keys():
                        image = req_data['data']['image']
                        if image != user_id.image_1920:
                            user_id.image_1920 = image
                    return valid_response({'message': "User Data Updated."})
                return invalid_response("no_user_data", "No name or image found.", 200)
        except Exception as e:
            _logger.exception("Error while updating user data for payload: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while updating user data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def post_batch_validate_data(payload):

        package_id = False
        package_obj = False
        stock_quant_package = request.env['stock.quant.package']
        params = ["batch_id", "create_backorder", "move_line_ids"]
        req_data = payload if len(payload) > 0 else json.loads(
            request.httprequest.data.decode())  # convert the bytes format to dict format
        req_params = {key: req_data.get(key) for key in params if req_data.get(key)}
        batch_id, move_line_ids = (
            req_params.get("batch_id"),
            req_params.get("move_line_ids")
        )

        _logger.info("Updating Batch Picking Transfers")
        stock_picking_batch = request.env['stock.picking.batch']
        stock_move = request.env['stock.move']
        stock_move_line = request.env['stock.move.line']
        stock_prod_lot = request.env['stock.lot']

        stock_picking_batch_obj = stock_picking_batch.sudo().search([('id', '=', req_params.get("batch_id"))])

        if stock_picking_batch_obj:
            if stock_picking_batch_obj.state == 'done':
                if 'sync_batch_pickings' in req_data:
                    return {'code': "already_validated", 'message': "This Batch is already done.",
                            'batch_id': stock_picking_batch_obj.id, 'sync_batch_pickings': True}
                return {'status': False, 'code': "already_validated", 'message': "This Batch is already done.",
                        'batch_id': stock_picking_batch_obj.id}
                # return invalid_response("already_validated", "This Batch is already done.", 200)

            if stock_picking_batch_obj.state == 'cancel':
                if 'sync_batch_pickings' in req_data:
                    return {'code': "batch_cancelled", 'message': "This Batch is Cancelled.",
                            'batch_id': stock_picking_batch_obj.id, 'sync_batch_pickings': True}
                return {'status': False, 'code': "batch_cancelled", 'message': "This Batch is Cancelled.",
                        'batch_id': stock_picking_batch_obj.id}
                # return invalid_response("batch_cancelled", "This Batch is Cancelled.", 200)

            if move_line_ids:
                product_package_list = {}

                for move_line in move_line_ids:
                    lot_id = False
                    lot_name = False
                    if move_line.get('lot_id') and isinstance(move_line.get('lot_id'), str):
                        #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                        # lot_detail = stock_prod_lot.sudo().search([
                        #     ('name', '=', move_line.get('lot_id')),
                        #     ('product_id', '=', move_line.get('product_id')),
                        #     ('company_id', '=', request.env.user.company_id.id)
                        # ], limit=1)
                        lot_detail = stock_prod_lot.sudo().search([
                            ('name', '=', move_line.get('lot_id')),
                            ('product_id', '=', move_line.get('product_id')),
                        ], limit=1)

                        if not lot_detail:
                            lot_detail = stock_prod_lot.create({
                                'name': move_line.get('lot_id'),
                                'product_id': move_line.get('product_id'),
                                'company_id': request.env.user.company_id.id,
                            })

                        if stock_picking_batch_obj.picking_type_id.code in ['outgoing', 'internal']:
                            # for Delivery Orders and Internal transfer
                            lot_id = lot_detail.id
                        if stock_picking_batch_obj.picking_type_id.code == 'incoming':  # for Receipts
                            if stock_picking_batch_obj.picking_type_id.use_existing_lots:  # Use Existing lots enabled
                                lot_id = lot_detail.id
                            else:  # Use Create New lots enabled
                                lot_name = move_line.get('lot_id')

                    if move_line.get("id"):  # if move.line id exists in the system.
                        move_line_obj = stock_move_line.sudo().browse(move_line.get("id"))

                        # move_line_obj.reserved_uom_qty = 0 #NOTE: reserved_uom_qty not available in v17
                        move_line_obj.quantity = move_line.get('quantity_done')
                        move_line_obj.lot_id = lot_id
                        move_line_obj.lot_name = lot_name

                        if move_line.get('product_package'):

                            if move_line['product_package'] in product_package_list:
                                move_line_obj.result_package_id = product_package_list[move_line.get('product_package')]

                            else:
                                package_obj = stock_quant_package.search(
                                    [('name', '=', move_line.get('product_package'))], limit=1)
                                if not package_obj:
                                    package_obj = stock_quant_package.create(
                                        {
                                            'name': move_line.get('product_package'),
                                            'package_use': 'disposable'
                                        })
                                move_line_obj.result_package_id = package_obj.id

                                product_package_list.update({move_line['product_package']: package_obj.id})

                        elif isinstance(move_line.get('product_packages_id'), int):
                            move_line_obj.result_package_id = move_line.get('product_packages_id')
                        # move_line_obj.result_package_id = move_line.get('product_packages_id')

                    else:  # if move.line id does not exist, create new record.
                        move_obj = stock_move.sudo().search([
                            ('picking_id', '=', move_line.get("picking_id")),
                            ('product_id', '=', move_line.get('product_id')),
                        ])

                        if move_line.get('product_package'):

                            if move_line['product_package'] in product_package_list:
                                package_id = product_package_list[move_line.get('product_package')]

                            else:
                                package_obj = stock_quant_package.search(
                                    [('name', '=', move_line.get('product_package'))], limit=1)
                                if not package_obj:
                                    package_obj = stock_quant_package.create(
                                        {
                                            'name': move_line.get('product_package'),
                                            'package_use': 'disposable'
                                        })
                                package_id = package_obj.id
                                product_package_list.update({move_line['product_package']: package_id})

                        elif isinstance(move_line.get('product_packages_id'), int):
                            package_id = move_line.get('product_packages_id')

                        vals = {
                            'picking_id': move_line.get("picking_id"),
                            'batch_id': stock_picking_batch_obj.id,
                            'move_id': move_obj.id,
                            'product_id': move_obj.product_id.id,
                            'quantity': move_line.get('quantity_done'),
                            'product_uom_id': move_obj.product_uom.id,
                            'location_id': move_obj.location_id.id,
                            'location_dest_id': move_obj.location_dest_id.id,
                            'lot_id': lot_id,
                            'lot_name': lot_name,
                            'result_package_id': package_id,
                        }
                        request.env['stock.move.line'].create(vals)

                # stock_picking_batch_obj.action_done()
                pickings = stock_picking_batch_obj.mapped('picking_ids').filtered(lambda picking: picking.state not in ('cancel', 'done'))

                if 'create_backorder' in req_data and not req_data.get('create_backorder'):
                        stock_picking_batch_obj = stock_picking_batch_obj.with_context(picking_ids_not_to_backorder = pickings.ids)
                stock_picking_batch_obj.with_context(skip_immediate=True, skip_sms=True,
                                                 skip_backorder=True).action_done()

                if stock_picking_batch_obj.state == 'done':
                    if 'sync_batch_pickings' in req_data:
                        return {'code': "success", 'message': "Batch Transfer is validated.",
                                'batch_id': stock_picking_batch_obj.id, 'sync_batch_pickings': True}
                    return {'status': True, 'code': "success", 'message': "Batch Transfer is validated.",
                            'batch_id': stock_picking_batch_obj.id}
                else:
                    if 'sync_batch_pickings' in req_data:
                        return {'code': "fail", 'message': "Batch Transfer is failed to validate.",
                                'batch_id': stock_picking_batch_obj.id, 'sync_batch_pickings': True}
                    return {'status': False, 'code': "fail", 'message': "Batch Transfer is failed to validate.",
                            'batch_id': stock_picking_batch_obj.id}

                # stock_picking_objs = stock_picking_batch_obj.picking_ids

                # if stock_picking_objs:
                #     for stock_picking_obj in stock_picking_objs:
                #         stock_picking_obj.with_context(skip_immediate=True, skip_sms=True,
                #                                         skip_backorder=True,
                #                                         picking_ids_not_to_backorder=stock_picking_obj.ids
                #                                         ).button_validate()

                #     if 'sync_batch_pickings' in req_data:
                #         return {'code': "success", 'message': "Batch Transfer is validated.",
                #                 'batch_id': stock_picking_batch_obj.id}
                #     return {'status': True, 'code': "success", 'message': "Batch Transfer is validated.",
                #                 'batch_id': stock_picking_batch_obj.id}
                #     # return valid_response({'message': "Batch Transfer is validated.", 'batch_id': stock_picking_batch_obj.id})
                # else:
                #     if 'sync_batch_pickings' in req_data:
                #         return {'code': "picking_ids_empty", 'message': "Pickings are empty.",
                #                 'batch_id': stock_picking_batch_obj.id}
                #     return {'status': False, 'code': "picking_ids_empty", 'message': "Pickings are empty.",
                #                 'batch_id': stock_picking_batch_obj.id}
                # return invalid_response("picking_ids_empty", "Pickings are empty.", 200)

            else:
                if 'sync_batch_pickings' in req_data:
                    return {'code': "move_line_ids_empty", 'message': "Move lines are empty.",
                            'batch_id': stock_picking_batch_obj.id, 'sync_batch_pickings': True}
                return {'status': False, 'code': "move_line_ids_empty", 'message': "Move lines are empty.",
                        'batch_id': stock_picking_batch_obj.id}
                # return invalid_response("move_line_ids_empty", "Move lines are empty.", 200)
        else:
            if 'sync_batch_pickings' in req_data:
                return {'code': "batch_picking_not_exists",
                        'message': "This batch transfer was not found in the system.",
                        'batch_id': req_params.get("batch_id"), 'sync_batch_pickings': True}
            return {'status': False, 'code': "batch_picking_not_exists",
                    'message': "This batch transfer was not found in the system.",
                    'batch_id': req_params.get("batch_id")}
            # return invalid_response("move_line_ids_empty", "Move lines are empty.", 200)
        
    @validate_token
    @http.route("/api/post_batch_validate", type="json", auth="none", methods=["POST"], csrf=False)
    def post_batch_validate(self, **payload):
        _logger.info("/api/post_batch_validate payload: %s", payload)

        try:
            res = self.post_batch_validate_data(payload)

            if isinstance(res, dict):
                if res.get('sync_batch_pickings'):
                    return res
                elif res.get('status'):
                    return valid_response(res)
                else:
                    return invalid_response(res['code'], res['message'], 200)
            else:
                return invalid_response('bad_request', 'Unknown Error', 200)

            # for rec in res:
            #     if 'sync_batch_pickings' in rec:
            #         return rec
            #     elif rec.get('status') and 'batch_id' in rec:
            #         return valid_response(res)
            # else:
            #     return invalid_response(res['code'], res['message'], 200)

        except Exception as e:
            _logger.exception("Error while validating batch picking for payload: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while Validating Batch Picking.'
            return invalid_response('bad_request', error_msg, 200)

    @validate_token
    @http.route("/api/sync_batch_post_picking_validate", type="json", auth="none", methods=["POST"], csrf=False)
    def sync_batch_post_picking_validate(self, **payload):
        _logger.info("/api/sync_batch_post_picking_validate payload: %s", payload)

        try:
            req_data = json.loads(
                request.httprequest.data.decode())  # convert the bytes format to `list of dict` format
            batch_res = []
            for data in req_data['data']:
                data['sync_batch_pickings'] = True
                response = self.post_batch_validate(**data)
                response.pop('sync_batch_pickings')
                batch_res.append(response)
            return valid_response(batch_res)
        except Exception as e:
            _logger.exception("Error while validating batch picking for payload: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while validating batch picking.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def _post_stock_quant_search_domain(self, quant, lot_id, product_package, owner_id, product_obj):
        domain= [('location_id.usage', 'in', ['internal', 'transit']),
                                ('location_id', '=', quant.get('location_id')),
                                ('product_id', '=', quant.get('product_id')),
                                ('lot_id', '=', lot_id), ('package_id', '=', product_package),
                                ('owner_id', '=', owner_id),
                                ('company_id','=',product_obj.company_id.id)]
        
        return domain

    @staticmethod
    def post_stock_quants_data(self, payload):

        params = ["stock_quant"]
        req_data = payload if len(payload) > 0 else json.loads(
            request.httprequest.data.decode())
        req_params = {key: req_data.get(key) for key in params if req_data.get(key)}
        stock_quant_data = req_params.get("stock_quant")

        _data_included_in_body = all([stock_quant_data])
        if not _data_included_in_body:
            return {"status": False, 'code': "post_data_error", 'message': "Data is not valid, please check again",
                    'picking_id': req_data['stock_quant']}
        else:
            _logger.info("Updating Stock Quant Data")
            stock_count = 0
            product_package = False
            stock_quant_obj = False
            lot_id = False
            owner_id = False
            stock_prod_lot = request.env['stock.lot']
            stock_quant = request.env['stock.quant']
            stock_quant_package = request.env['stock.quant.package']

            if stock_quant_data:
                for quant in stock_quant_data:
                    try:
                        if quant.get('product_id'):
                            product_obj = request.env['product.product'].search([('id','=',quant.get('product_id'))])
                        if isinstance(quant.get('package_id'), int):
                            product_package = quant.get('package_id')
                        elif not quant.get('package_id'):
                            product_package = False
                        else:
                            package_obj = stock_quant_package.sudo().search(
                                [('name', '=', quant.get('package_id')),('company_id','=', product_obj.company_id.id)], limit=1)
                            if not package_obj:
                                package_obj = stock_quant_package.create(
                                    {
                                        'name': quant.get('package_id'),
                                        'package_use': 'disposable'
                                    })
                            product_package = package_obj.id

                        if quant.get('lot_id'):
                            #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                            # lot_detail = stock_prod_lot.sudo().search([
                            #     ('name', '=', quant.get('lot_id')),
                            #     ('product_id', '=', quant.get('product_id')),
                            #     ('company_id', '=', request.env.user.company_id.id)], limit=1)
                            lot_detail = stock_prod_lot.sudo().search([
                                ('name', '=', quant.get('lot_id')),
                                ('product_id', '=', quant.get('product_id')),
                                ('company_id','=',product_obj.company_id.id)], limit=1)

                            if not lot_detail:
                                lot_detail = stock_prod_lot.create({
                                    'name': quant.get('lot_id'),
                                    'product_id': quant.get('product_id'),
                                    'company_id': product_obj.company_id.id,
                                })
                            lot_id = lot_detail.id

                        if quant.get('owner_id'):
                            owner_id = quant.get('owner_id')

                        vals = {
                            'location_id': quant.get('location_id'),
                            'product_id': quant.get('product_id'),
                            'lot_id': lot_id,
                            'package_id': product_package,
                            'owner_id': owner_id,
                            'inventory_quantity': quant.get('inventory_quantity'),
                            'inventory_date': quant.get('inventory_date'),
                            'company_id': product_obj.company_id.id
                        }
                        # product_obj = product.sudo().search([('id','=',int(quant.get('product_id')))], limit = 1)
                        # if product_obj:
                        #     product_categ_id = product_obj.categ_id.id
                        #NOTE:('company_id', '=', request.env.user.company_id.id) is being removed from the domain to show records irrespective of user's default company
                        # domain = [('location_id.usage', 'in', ['internal', 'transit']),
                        #         ('location_id', '=', quant.get('location_id')),
                        #         ('product_id', '=', quant.get('product_id')),
                        #         #   ('product_categ_id','=',product_categ_id),
                        #         ('lot_id', '=', lot_id), ('package_id', '=', product_package),
                        #         #   ('product_uom_id','=',product_obj.uom_id.id),
                        #         ('owner_id', '=', owner_id), ('company_id', '=', request.env.user.company_id.id)]
                        # domain = [('location_id.usage', 'in', ['internal', 'transit']),
                        #         ('location_id', '=', quant.get('location_id')),
                        #         ('product_id', '=', quant.get('product_id')),
                        #         #   ('product_categ_id','=',product_categ_id),
                        #         ('lot_id', '=', lot_id), ('package_id', '=', product_package),
                        #         #   ('product_uom_id','=',product_obj.uom_id.id),
                        #         ('owner_id', '=', owner_id),
                        #         ('company_id','=',product_obj.company_id.id)]
                        
                        domain = self._post_stock_quant_search_domain(self,quant, lot_id, product_package, owner_id, product_obj)

                        stock_quant_available = stock_quant.sudo().search(domain, limit=1)
                        if stock_quant_available:
                            stock_quant_available.write(vals)
                            stock_quant_available.action_apply_inventory()
                            stock_count = stock_count + 1
                        else:
                            stock_quant_obj = stock_quant.create(vals)
                            if stock_quant_obj:
                                stock_quant_obj.action_apply_inventory()
                                stock_count = stock_count + 1
                                if not request.env['ir.config_parameter'].sudo().get_param('stock.skip_quant_tasks'):
                                    stock_quant_obj._quant_tasks()
                                # return {"status": True, 'message': "Stock quant is created", 'quant_id': stock_quant_obj.id}
                            else:
                                return {"status": False, 'code': "not_stock_quant_created",
                                        'message': "Stock quant is not created",
                                        'product_id': quant.get('product_id'), 'location_id': quant.get('location_id')}
                    except Exception as e:
                        _logger.exception("Error while creating stock quants data.", e)
                        return {"status": False, 'type': "bad_request",
                                        'message': "Error while creating stock quants data.",
                                        'product_id': quant.get('product_id'), 'location_id': quant.get('location_id')}
                if stock_count == len(stock_quant_data):
                    return {"status": True, 'message': "Stock quant is created and updated with quantity"}
            else:
                return {"status": False, 'code': "stock_quant_data", 'message': "Stock quant datas are empty."}

    @validate_token
    @http.route("/api/post_stock_quants", type="json", auth="none", methods=["POST"], csrf=False)
    def post_stock_quants(self, **payload):
        """
            create stock quant info.
        """
        _logger.info("/api/post_stock_quants POST payload: %s", payload)
        try:
            response_data = self.post_stock_quants_data(self, payload)
            if isinstance(response_data, dict):
                if response_data['status']:
                    return valid_response(response_data)
                else:
                    return invalid_response(response_data.get('code'), response_data.get('message'))
        except Exception as e:
            _logger.exception("Error while creating stock quants data: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while creating stock quants data.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def post_put_in_pack_data(payload):
        params = ["picking_id", "move_line_ids"]
        req_data = payload if len(payload) > 0 else json.loads(
            request.httprequest.data.decode())  # convert the bytes format to dict format
        req_params = {key: req_data.get(key) for key in params if req_data.get(key)}
        picking_id, move_line_ids = (
            req_params.get("picking_id"),
            req_params.get("move_line_ids")
        )
        picking_obj = request.env['stock.picking'].sudo().search([('id', '=', picking_id)])
        if not picking_obj:
            return {"status": False, 'code': picking_id, 'message': "No picking found."}

        line_ids = []
        for val in move_line_ids:
            if val.get("id"):
                current_line_obj = request.env['stock.move.line'].sudo().search([('id', '=', val["id"])])
                if current_line_obj and current_line_obj.picking_id and current_line_obj.picking_id.id == picking_id:
                    request.env['stock.move.line'].sudo().search([('id', '=', val["id"])]).write({
                        "quantity": int(val.get("quantity_done", 0))
                    })
                    line_ids.append(val["id"])
                else:
                    return {"status": False, 'code': val.get("id"), 'message': "invalid move line id."}

        for val in move_line_ids:
            if not val.get("id"):
                new_line_obj = request.env['stock.move.line'].sudo().search([
                    ('picking_id', '=', int(picking_id)), '|',
                    ('product_id', '=', int(val.get('product_id'))),
                    ('id', 'in', line_ids),
                ], limit=1)
                if not new_line_obj:
                    return {"status": False, 'code': [int(picking_id), int(val.get('product_id'))],
                            'message': "No move line found with given picking id and product id."}

                new_line_obj.copy(default={'reserved_uom_qty': 0, 'quantity': val.get('quantity_done')})
                line_ids.append(new_line_obj.id)

        move_line_obj = request.env['stock.move.line'].sudo().search([('id', 'in', line_ids)])
        _logger.info("Data for post_put_in_pack_data: %s, %s", picking_obj, move_line_obj)

        # package_obj = picking_obj._put_in_pack(move_line_obj, create_package_level=True)
        package_obj = picking_obj._put_in_pack(move_line_obj)
        if package_obj:
            response_data = [{
                "id": package_obj.id,
                "name": package_obj.name,
                "package_type_id": package_obj.package_type_id.id,
                "pack_date": package_obj.pack_date,
                "shipping_weight": package_obj.shipping_weight,
                "weight_uom_name": package_obj.weight_uom_name,
                "weight": package_obj.weight,
                "message": "Picking is updated with package."
            }]
            return response_data
        else:
            return {"status": False, 'code': "package_obj", 'message': "Package is not created."}

    @validate_token
    @http.route("/api/post_put_in_pack", type="json", auth="none", methods=["POST"], csrf=False)
    def post_put_in_pack(self, **payload):
        _logger.info("/api/post_put_in_pack payload: %s", payload)
        try:
            res = self.post_put_in_pack_data(payload)
            if res:
                if isinstance(res, list):
                    return valid_response(res)
                else:
                    return invalid_response(res['code'], res['message'], 200)

        except Exception as e:
            _logger.exception("Error while creating new package for payload: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error while creating package.'
            return invalid_response('bad_request', error_msg, 200)

    @staticmethod
    def post_sync_move_line_data(self, payload):
        req_data = payload if len(payload) > 0 else json.loads(request.httprequest.data.decode())

        response_data = []
        for vals in req_data.get("data"):
            params = ["picking_id", "move_line_ids"]  # convert the bytes format to dict format
            req_params = {key: vals.get(key) for key in params if vals.get(key)}
            picking_id, move_line_ids = (
                req_params.get("picking_id"),
                req_params.get("move_line_ids")
            )

            picking_obj = request.env['stock.picking'].sudo().search([('id', '=', picking_id)])
            if not picking_obj:
                return {"status": False, 'code': picking_id, 'message': "No picking found."}

            if move_line_ids:
                line_pack_dict = defaultdict(list)
                res_str, picking_response = self._prepare_picking_data(self, picking_obj, move_line_ids, line_pack_dict)

                # line_ids = []
                # for val in move_line_ids:
                #     if val.get("id"):
                #         current_line_obj = request.env['stock.move.line'].sudo().search([('id', '=', val.get("id"))])
                #         if current_line_obj and current_line_obj.picking_id and current_line_obj.picking_id.id == picking_id:
                #             request.env['stock.move.line'].sudo().search([('id', '=', val.get("id"))]).write({
                #                 "qty_done": int(val.get("quantity_done", 0))
                #             })
                #             line_ids.append(val["id"])
                #         else:
                #             return {"status": False, 'code': val.get("id"), 'message': "invalid move line id."}
                #
                # for val in move_line_ids:
                #     if not val.get("id"):
                #         new_line_obj = request.env['stock.move.line'].sudo().search([
                #             ('picking_id', '=', int(picking_id)), '|',
                #             ('product_id', '=', int(val.get('product_id'))),
                #             ('id', 'in', line_ids),
                #         ], limit=1)
                #         if not new_line_obj:
                #             return {"status": False, 'code': [int(picking_id), int(val.get('product_id'))], 'message': "No move line found with given picking id and product id."}
                #         new_line_obj.copy(default={'reserved_uom_qty': 0, 'qty_done': val.get('quantity_done')})
                #         line_ids.append(new_line_obj.id)
                #
                # if put_in_pack:
                #     move_line_obj = request.env['stock.move.line'].sudo().search([('id', 'in', line_ids)])
                #     _logger.info("Data for post_put_in_pack_data: %s, %s", picking_obj, move_line_obj)
                #
                #     package_obj = picking_obj._put_in_pack(move_line_obj, create_package_level=True)
                if picking_response:
                    response_data.append({"status": True, "message": f'Transfer {picking_obj.name} is updated',
                                        "picking_id": picking_id})
                else:
                    return {"status": False, 'code': "package_obj",
                            'message': f'Transfer {picking_obj.name} is not updated',
                            'picking_id': picking_id}
            else:
                return {"status": False, 'code': "no move_line_id", 'message': "move_line_ids are not found",
                        'picking_id': picking_id}
        return response_data

    @validate_token
    @http.route("/api/post_sync_move_line", type="json", auth="none", methods=["POST"], csrf=False)
    def post_sync_move_line(self, **payload):
        _logger.info("/api/post_put_in_pack payload: %s", payload)
        try:
            res = self.post_sync_move_line_data(self, payload)
            if res:
                if isinstance(res, list):
                    return valid_response(res)
                else:
                    return invalid_response(res.get('code'), res.get('message'), 200)

        except Exception as e:
            _logger.exception("Error in sync move line data for payload: %s", payload)
            err = _serialize_exception(e)
            if err.get('message'):
                error_msg = err.get('message')
            else:
                error_msg = 'Error in sync move line data.'
            return invalid_response('bad_request', error_msg, 200)




    # NOTE: transferred to bista_wms_sales_extensions
    # 16 to 17
    # @validate_token
    # @http.route("/api/post_package_weight_update", type="json", auth="none", methods=["POST"], csrf=False)
    # def post_package_weight_update(self, **payload):
    #     _logger.info("/api/post_package_weight_update: %s", payload)
    #     try:
    #         res = self.post_package_weight_update_data(self, payload)
    #         if res:
    #             if isinstance(res, list):
    #                 return valid_response(res)
    #             else:
    #                 return invalid_response(res.get('code'), res.get('message'), 200)

    #     except Exception as e:
    #         _logger.exception("Error while updating package weight for payload: %s", payload)
    #         err = _serialize_exception(e)
    #         if err.get('message'):
    #             error_msg = err.get('message')
    #         else:
    #             error_msg = 'Error while updating package weight.'
    #         return invalid_response('bad_request', error_msg, 200)

    # @staticmethod
    # def post_package_weight_update_data(self, payload):
    #     params = ["product_packages"]
    #     req_data = payload if len(payload) > 0 else json.loads(
    #         request.httprequest.data.decode())
    #     req_params = {key: req_data.get(key) for key in params if req_data.get(key)}
    #     product_package_data = req_params.get("product_packages")

    #     _data_included_in_body = all([product_package_data])
    #     if not _data_included_in_body:
    #         return {"status": False, 'code': "post_data_error", 'message': "Data is not valid, please check again",
    #                 'product_packages': req_data['product_packages']}
    #     else:
    #         response_data = []
    #         package_id = False
    #         stock_quant_package = request.env['stock.quant.package'].sudo()

    #         if product_package_data:
    #             for package_data in product_package_data:
    #                 if not package_data.get('package_id'):
    #                     return {"status": False, 'code': "no_data", 'message': "No Package id is provided"}
    #                 if not package_data.get('shipping_weight'):
    #                     return {"status": False, 'code': "no_data", 'message': 'No shipping weight is provided',
    #                             'package_id': package_data['package_id']}
    #                 if isinstance(package_data.get('package_id'), int) and isinstance(
    #                         package_data.get('shipping_weight'), float):
    #                     package_id = package_data['package_id']
    #                     stock_quant_package_id = stock_quant_package.search([('id', '=', package_data['package_id'])])

    #                     if stock_quant_package_id:
    #                         stock_quant_package_id.write({'shipping_weight': package_data['shipping_weight']})
    #                         response_data.append({"status": True, 'message': "Shipping weight is updated",
    #                                             'package_id': f'{stock_quant_package_id.name}({stock_quant_package_id.id})'})
    #                         stock_quant_package_id = False

    #                     else:
    #                         return {"status": False, 'code': "not_found",
    #                                 'message': f'No Product Package found for id ({package_id})'}
    #                 else:
    #                     return {"status": False, 'code': "not_found",'message': 'Invalid data type'}
    #             if len(response_data) > 0:
    #                 return response_data
    #         else:
    #             return {"status": False, 'code': "not_data", 'message': 'No Product Package data provided'}
