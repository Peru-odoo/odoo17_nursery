# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2021 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import fields, models, api


class Picking(models.Model):
    _inherit = 'stock.picking'

    # rfid_tag = fields.Char(string="RFID Tag", copy=False,
    #                        help="RFID Tag number used for picking identification.")

    rfid_tag = fields.Many2one('rfid.tag', string='RFID Tag', readonly=1,
                               domain=[('usage_type', 'in', ('receipt', 'delivery', 'n_a')),
                                       ('picking_id', '=', False)])

    # _sql_constraints = [(
    #     'rfid_tag_uniq', 'unique (rfid_tag)',
    #     "A RFID tag cannot be linked to multiple Transfers."
    # )]