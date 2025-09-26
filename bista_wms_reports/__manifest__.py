# -*- encoding: utf-8 -*-
##############################################################################
#
# Bista Solutions Pvt. Ltd
# Copyright (C) 2023 (http://www.bistasolutions.com)
#
##############################################################################

{
    'name': "Bista WMS Reports",

    'summary': """Wms Reports and Product Label printing functionality as v16.""",

    'description': """
        This module adds Product Label printing functionality and transfer reports as v16.
    """,

    'author': "Bista Solutions Pvt. Ltd.",
    'website': "https://www.bistasolutions.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/13.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Operations/Inventory',
    'version': '18.0.1.0.0',

    'application': True,

    # any module necessary for this one to work correctly
    'depends': ['base', 'stock', 'product', 'product_expiry', 'stock_picking_batch'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        # 'data/data.xml',

        'views/res_config_settings_views.xml',
        'views/bista_stock_picking_views.xml',

        # 'report/product_reports.xml',
        'report/product_product_templates.xml',
        'report/report_lot_barcode.xml',
        # 'report/picking_templates.xml',

        'report/report_stockpicking_operations.xml',
        'report/report_picking_batch.xml',
        'report/wms_report_location_barcode.xml',
        'report/stock_lot_barcode.xml',
        'report/report_package_barcode.xml',
        'wizard/bista_wms_package_wizard_view.xml',
    ],
}
