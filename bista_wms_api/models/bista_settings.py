import logging
from odoo import fields, models, api
from odoo.addons.bista_wms_api.common import prepare_config_settings

_logger = logging.getLogger(__name__)


class BistaConfigSettings(models.Model):
    _name = 'bista.wms.config.settings'
    _description = 'Bista Config Seiings'
    _rec_name = 'warehouse_name'

    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    user_id = fields.Many2one('res.users', string='User')
    warehouse_name = fields.Char(related='warehouse_id.name')
    company_id = fields.Many2one('res.company', string='Company')
    product_packages = fields.Boolean(string='Product Packages')
    product_packaging = fields.Boolean(string='Product Packaging')
    wms_licensing_key = fields.Char(string='Wms Licensing Key')
    batch_transfer = fields.Boolean(string='Batch Transfer')
    barcode_scanner = fields.Boolean(string='Barcode Scanner')
    delivery_method = fields.Boolean(string='Delivery Method')
    product_variants = fields.Boolean(string='Variants')
    units_of_measure = fields.Boolean(string='Units of Measure')
    storage_locations = fields.Boolean(string='Storage location')
    multi_step_routes = fields.Boolean(string='Mult-steps Routes')
    storage_categories = fields.Boolean(string='Storage Categories')
    quality = fields.Boolean(string='Quality')
    barcode_gst1 = fields.Boolean(string='Print GS-1 Barcode')
    lot_on_invoice = fields.Boolean(string='Display Lot on Invoice')
    consignment = fields.Boolean(string='Consignment')
    expiration_dates = fields.Boolean(string='Expiration Dates')
    use_qr_code = fields.Boolean(string='QR Code')
    use_qr_code_print_label = fields.Boolean(string='Product Label')
    use_qr_code_picking_operations = fields.Boolean(string='Picking Operations')
    use_qr_code_batch_operations = fields.Boolean(string='Batch/Wave Operations')

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    @api.model_create_multi
    def create(self, vals_list):
        warehouse = super(StockWarehouse, self).create(vals_list)
        for warehouse_id in warehouse:
            warehouse_obj = self.env['bista.wms.config.settings'].search(
                [('warehouse_id', '=', warehouse_id.id), ('company_id', '=', warehouse_id.company_id.id)], limit=1)
            if not warehouse_obj:
                prepare_config_settings(self, warehouse_id, 'create')
        return warehouse

    def write(self, vals):
        warehouse = super(StockWarehouse, self).write(vals)
        for warehouse_id in self:
            warehouse_obj = self.env['bista.wms.config.settings'].search(
                [('warehouse_id', '=', warehouse_id.id), ('company_id', '=', warehouse_id.company_id.id)], limit=1)
            if warehouse_obj:
                prepare_config_settings(self, warehouse_obj, 'update')
            else:
                prepare_config_settings(self, warehouse_id, 'create')
        return warehouse
