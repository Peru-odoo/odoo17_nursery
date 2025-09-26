from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BistaWMSPackage(models.TransientModel):
    _name = 'bista.wms.package'
    _description = 'Wizard for packages'

    result_package_ids = fields.Many2many('stock.quant.package',relation='bista_wms_package_stock_quant_package_rel', string="WMS Package")
    print_option = fields.Selection([
        ('package_barcode_with_content', 'Package Barcode with Content'),
        ('package_barcode_pdf', 'Package Barcode (PDF)'),
        ('package_barcode_zpl', 'Package Barcode (ZPL)'),
        ('package_content_zpl', 'Package Content (ZPL)')], string="Print Options", default='package_barcode_with_content', required=True)
    def _prepare_report_data(self):
        if self.print_option == 'package_barcode_with_content':
            xml_id = 'stock.action_report_quant_package_barcode'
        elif self.print_option == 'package_barcode_pdf':
            xml_id = 'stock.action_report_quant_package_barcode_small'
        elif self.print_option == 'package_barcode_zpl':
            xml_id = 'stock.label_package_template'
        elif self.print_option == 'package_content_zpl':
            xml_id = 'printnode_base.action_report_package_slip_zpl'
        else:
            xml_id = ''

        if self.result_package_ids:
            packages = self.result_package_ids.ids
        else:
            raise UserError(_("No product to print, if the product is archived please unarchive it before printing its label."))
        return xml_id

    def process(self):
        self.ensure_one()
        xml_id = self._prepare_report_data()
        if not xml_id:
            raise UserError(_('Unable to find report template for %s format', self.print_format))
        packages = self.env['stock.quant.package'].browse(self.result_package_ids.ids)
        return self.env.ref(xml_id).report_action(packages)

