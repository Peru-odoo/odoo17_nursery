{
    'name': 'Negative Stock Control',  
    #'version': '17.0.1.0.0',  
    'summary': 'Add option to allow or disallow negative stock globally', 
    'author': 'Basel Amr Triple A',  
    'depends': ['stock'],  
    'data': [
        'views/stock_config_settings_view.xml',
        'security/ir.model.access.csv',
    ],
    'installable': True,  
    'application': False,  
}
