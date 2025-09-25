from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

operation_type = [('pick', 'Pick'), ('pack', 'Pack'), ('in_type', 'In Type'),
        ('out_type', 'Out Type'), ('internal', 'Internal')]

class ResUsers(models.Model):
    _inherit = "res.users"

    warehouse_id = fields.Many2one("stock.warehouse", string="Allowed Warehouse")

    def write(self, vals):
        if 'warehouse_id' in vals:
            if self.warehouse_id.id != vals['warehouse_id']:
                assigned_picking = self.env['stock.picking'].search(
                    [('user_id', '=', self.id), ('state', 'not in', ['done', 'cancel']),
                     ('picking_type_id.warehouse_id', '=', self.warehouse_id.id)])
                assigned_batch_picking = self.env['stock.picking.batch'].search(
                    [('user_id', '=', self.id), ('state', 'not in', ['done', 'cancel']),
                     ('picking_type_id.warehouse_id', '=', self.warehouse_id.id)])

                if assigned_picking or assigned_batch_picking:
                    raise ValidationError(_("This user is already assigned to Transfer(s) that are in Ready state. "
                                            "Please remove this user from those Transfer(s) & try again."))
        return super(ResUsers, self).write(vals)

    def action_show_transfer(self):
        self.ensure_one()
        ctx = self._context
        if 'batch_transfer' in ctx and ctx['batch_transfer'] == 1:
            name = _('Batch Transfers')
            res_model = 'stock.picking.batch'
        else:
            name = _('Transfers')
            res_model = 'stock.picking'
        return {
            'name': name,
            'view_mode': 'list,form',
            'res_model': res_model,
            'type': 'ir.actions.act_window',
            'context': {'create': False, 'delete': False},
            'domain': [('state', 'not in', ['done', 'cancel']), ('user_id', '=', self.id)],
            'target': 'current',
        }


class StockPicking(models.Model):
    _inherit = "stock.picking"

    user_id = fields.Many2one(default=False)
    warehouse_id = fields.Many2one(related='picking_type_id.warehouse_id')

    # NOTE: no longer is used in v17. the following domain is set through view
    # @api.onchange('picking_type_id')
    # def onchange_picking_type_id(self):
    #     domain = [('groups_id', 'in', self.env.ref('stock.group_stock_user').id), ('share', '=', False)]
    #     if self.picking_type_id:
    #         warehouse_id = self.picking_type_id.warehouse_id
    #         return {'domain': {'user_id': domain + [('warehouse_id', '=', warehouse_id.id)]}}
    #     else:
    #         return {'domain': {'user_id': domain}}


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    warehouse_id = fields.Many2one(related='picking_type_id.warehouse_id')
    operation_type = fields.Selection(related = 'picking_type_id.operation_type', string = 'Operation State')

    # NOTE: no longer is used in v17. the following domain is set through view
    # @api.onchange('picking_type_id')
    # def onchange_picking_type_id(self):
    #     domain = [('groups_id', 'in', self.env.ref('stock.group_stock_user').id), ('share', '=', False)]
    #     if self.picking_type_id:
    #         warehouse_id = self.picking_type_id.warehouse_id
    #         return {'domain': {'user_id': domain + [('warehouse_id', '=', warehouse_id.id)]}}
    #     else:
    #         return {'domain': {'user_id': domain}}


# class StockQuantPackages(models.Model):
#     _inherit = 'stock.quant.package'

#     @api.model
#     def default_package_sequence(self):
#         print('context---------------', self.env.context)
#         if self.env.context.get('is_mobile_app'):
#             return self.env['ir.sequence'].next_by_code('stock.quant.packages')
#         else:
#             return self.env['ir.sequence'].next_by_code('stock.quant.package') or _('Unknown Pack')

#     name = fields.Char(default=default_package_sequence)


class Sequence(models.Model):
    _inherit = 'ir.sequence'

    is_mobile_app = fields.Boolean(string='For Mobile App')

class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'
    
    operation_type = fields.Selection(operation_type, string = 'Operation Type')
    
class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    operation_type = fields.Selection(related = 'picking_type_id.operation_type', string = 'Operation State')
        
    
class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    @api.model
    def action_pick_operation(self):
        """make pick operation field true in operation type"""
        multi_steps_routing = self.env.user.has_group(
            'stock.group_adv_location')
        if multi_steps_routing:
            warehouse_obj = self.env['stock.warehouse'].search(
                [('company_id', '=', self.env.user.company_id.id)])
            for warehouse in warehouse_obj:
                pick_type_available = warehouse.pick_type_id
                pack_type_available = warehouse.pack_type_id
                in_type_available = warehouse.in_type_id
                out_type_available = warehouse.out_type_id
                internal_available = warehouse.int_type_id
                if pick_type_available and not pick_type_available.operation_type:
                    pick_type_available.operation_type = 'pick'
                if pack_type_available and not pack_type_available.operation_type:
                    pack_type_available.operation_type = 'pack'
                if in_type_available and not in_type_available.operation_type:
                    in_type_available.operation_type = 'in_type'
                if out_type_available and not out_type_available.operation_type:
                    out_type_available.operation_type = 'out_type'
                if internal_available and not internal_available.operation_type:
                    internal_available.operation_type = 'internal'

    @api.model_create_multi
    def create(self, vals_list):
        res = super(StockWarehouse, self).create(vals_list)
        multi_steps_routing = self.env.user.has_group(
            'stock.group_adv_location')
        if multi_steps_routing:
            for warehouse in res:
                pick_type_available = warehouse.pick_type_id
                pack_type_available = warehouse.pack_type_id
                in_type_available = warehouse.in_type_id
                out_type_available = warehouse.out_type_id
                internal_available = warehouse.int_type_id
                if pick_type_available and not pick_type_available.operation_type:
                    pick_type_available.operation_type = 'pick'
                if pack_type_available and not pack_type_available.operation_type:
                    pack_type_available.operation_type = 'pack'
                if in_type_available and not in_type_available.operation_type:
                    in_type_available.operation_type = 'in_type'
                if out_type_available and not out_type_available.operation_type:
                    out_type_available.operation_type = 'out_type'
                if internal_available and not internal_available.operation_type:
                    internal_available.operation_type = 'internal'

        return res
    