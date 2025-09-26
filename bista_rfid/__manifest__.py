# -*- coding: utf-8 -*-

{
    'name': "Bista RFID",

    'summary': """RFID Integration in Odoo.""",

    'description': """
        This Module will generate RFID code for Product Labels, Picking Operations.
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
    ],

    'external_dependencies': {
        'python': ['base64', 'xlrd'],
    },

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/product_views.xml',
        'views/product_template_views.xml',
        'views/stock_picking_views.xml',
        'views/stock_lot_views.xml',
        'views/rfid_tag_views.xml',
        'views/rfid_menu_views.xml',
        'wizard/rfid_tag_import_views.xml',
        'wizard/message_wizard_views.xml',
    ],
    'application': True,
}
