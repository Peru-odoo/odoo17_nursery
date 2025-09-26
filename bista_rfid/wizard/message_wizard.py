# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2021 (http://www.bistasolutions.com)
#
##############################################################################

from odoo import fields, models, api


class MessageWizard(models.TransientModel):
    _name = 'message.wizard'

    message_one = fields.Text('Message one', required=True, readonly=True)
    message_two = fields.Text('Message two', required=True, readonly=True)

    def action_ok(self):
        """ close wizard"""
        # return {'type': 'ir.actions.act_window_close'}
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
