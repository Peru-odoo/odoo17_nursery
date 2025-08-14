{
    "name": "All-in-One Secondary Unit of Measure",
    "version": "17.0.1.0.0",
    "summary": "Secondary UoM across Products, Sales, Purchase, Inventory, Accounting, and MRP.",
    "category": "Productivity",
    "license": "LGPL-3",
    "author": "You",
    "depends": [
        "product", "uom",
        "sale_management", "purchase",
        "stock", "account", "mrp"
    ],
    "data": [
        # groups first
        "security/secondary_uom_security.xml",
        # then views
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
        'views/purchase_order_views.xml',
        'views/stock_picking_views.xml',
        'views/account_move_views.xml',
        'views/stock_move_line_history_views.xml',
        # 'views/purchase_strip_subcontracting.xml',  # <— add this
    ],
    "installable": True,
    "application": False,
}
