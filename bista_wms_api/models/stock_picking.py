from odoo import fields, models, api, _


class Picking(models.Model):
    _inherit = "stock.picking"
   
    app_change_ids = fields.One2many("bista.app.change", "stock_picking_id", string="App Changes")

    @api.model
    def _read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        if self.env.context.get('user_id_filtering'):
            domain += [('user_id', '=', self.env.user.id)]
        res =  super()._read_group(domain, groupby, aggregates, having, offset, limit, order)
        return res
