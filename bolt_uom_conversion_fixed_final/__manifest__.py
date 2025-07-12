{
    "name": "Bolt UoM Conversion",
    "version": "1.0",
    "category": "Inventory",
    "summary": "Convert weight (kg/ton) to number of units",
    'depends': ['base', 'stock', 'product'],
    "data": [
        "security/ir.model.access.csv",
        "views/uom_bulk_calc_action.xml",
        "views/uom_bulk_calc_menu.xml",
        "views/uom_bulk_calc_view.xml"
    ],
    "installable": True,
    "application": False
}