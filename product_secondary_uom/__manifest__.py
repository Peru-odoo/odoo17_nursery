{
    'name': 'Secondary Unit of Measure_new',
    'version': '1.0',
    'summary': 'Manage secondary units for sales, purchases, inventory, and accounting',
    'description': '''
        This module allows you to manage and display secondary units of measure 
        across Sales, Purchase, Inventory, and Accounting modules. It also supports 
        automatic conversions and includes secondary UOMs in reports.
    ''',
    'category': 'Inventory',
    'author': 'Your Name or Company',
    'website': 'https://yourwebsite.com',
    'depends': ['sale', 'purchase', 'stock', 'account', 'product'],
    'data': [
        'security/ir.model.access.csv',

         'views/product_view.xml',

        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/account_invoice_views.xml',
        'views/sale_order_delivery_button.xml',
        #
        # 'report/sale_order_report_templates.xml',
        # 'report/picking_report_templates.xml',
        # 'report/invoice_report_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
