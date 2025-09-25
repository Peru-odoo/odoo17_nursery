# -*- coding: utf-8 -*-
{
    'name': "Bista WMS API",

    'summary': """APIs for WMS mobile app.""",

    'description': """
        This module includes the following features:
            - Customized Login API endpoint
            - 
    """,

    'author': "Bista Solutions Pvt. Ltd.",
    'website': "https://www.bistasolutions.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Technical',
    'version': '18.0.1.0.0',

    # any module necessary for this one to work correctly
    'depends': [
        'base',
        'product',
        'stock',
        # NOTE: transferred to bista_wms_api_purchase_extension:
        # 'purchase',
        # 'purchase_stock',
        'stock_picking_batch',
        # 'bista_wms_reports'
        # NOTE: transferred to bista_wms_api_sale_delivery_extension:
        # 'sale',
        # 'sale_stock',
        # 'delivery',
        
    ],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
        'data/data.xml',
        'data/ir_sequence.xml',
        'data/stock_warehouse_cron.xml',
        'views/res_users.xml',
        'views/stock_picking.xml',
        'views/res_config_settings_view.xml',
        'views/stock_location_view.xml',
        'views/bista_app_settings_menu.xml',
        'views/bista_wms_config_view.xml',
        'views/bista_app_changes_view.xml'
    ],
    'images': ['static/description/images/banner.gif'],
    "post_init_hook": "_post_init_pick_hook",
}
