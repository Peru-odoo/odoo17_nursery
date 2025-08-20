{
    "name": "real_estate Management",
    "version": "1.0",
    "depends": ["base", "web", "mail"],
    "author": "Your Company",
    "category": "real_estate",
    "description": "Manage properties, agents, bookings, and print reports.",
    "data": [
        "security/ir.model.access.csv",
        "views/menu.xml",
        "views/property_views.xml",
        "views/agent_views.xml",
        "views/booking_views.xml",
        "report/property_report.xml",
        "report/report_template.xml",
    ],
    "application": True,
}
