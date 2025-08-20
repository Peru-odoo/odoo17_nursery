{
    'name': 'Negative Stock Control',  # Module name shown in Odoo Apps list
    #'version': '17.0.1.0.0',  # Version format: OdooVersion.Major.Minor.Fix
    'summary': 'Add option to allow or disallow negative stock globally',  # Short description in Apps list
    'description': 'Blocks stock moves that would cause negative stock if the setting is disabled.',  # Longer description
    'author': 'Basel Amr Triple A',  # Your name or company
    'depends': ['stock'],  # This module needs Odoo's stock module to work
    'data': [
        'views/stock_config_settings_view.xml',
        'views/stock_location_views.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,  # Can be installed
    'application': False,  # Not a standalone app, but an extra feature
}
