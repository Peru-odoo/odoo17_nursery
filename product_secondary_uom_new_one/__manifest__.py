
{
    'name': 'Secondary Unit of Measure (Sale & Purchase)',
    'version': '1.0',
    'summary': 'Add secondary UOM to sale and purchase orders',
    'description': 'Display secondary units of measure in sale and purchase order lines',
    'category': 'Sales',
    'author': 'Basel Noor',
    'website': 'https://yourcompany.com',
    'depends': ['sale', 'purchase', 'stock', 'account', 'product'],
    'data': [
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/product_template_view.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
