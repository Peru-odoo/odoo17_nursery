from odoo import fields, models, api, _


class BistaAppChange(models.Model):
    
    _name = "bista.app.change"
    
    res_model = fields.Char("Resource Model", readonly=True)
    app_created = fields.Boolean(string="App Created", readonly=True)
    app_changes = fields.Html(string="App Changes", default="<p>0→0</p>", readonly=True)
    # picking_id = fields.Many2one("stock.picking", string="Picking ID")
    stock_picking_id = fields.Many2one("stock.picking", string="Stock Picking ID", readonly=True)
    app_changed_id = fields.Reference(selection=[('stock.picking', 'Transfer'),
                                                ('product.product', 'Product'), 
                                                ('stock.lot', 'Lot/Serial No.'),
                                                ('stock.move.line', 'Detailed Operations')],
                                                string="Ref ID", readonly=True)

