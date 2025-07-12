from odoo import models, fields, api

class UoMBulkCalcWizard(models.TransientModel):
    _name = 'uom.bulk.calc.wizard'
    _description = 'Bulk UoM Calculator Wizard'

    total_weight = fields.Float(string='Total Weight', required=True)
    weight_unit = fields.Selection([('kg', 'Kilograms'), ('ton', 'Tons')], string='Weight Unit', required=True)
    weight_per_unit = fields.Float(string='Weight per Unit (kg)', required=True)
    unit_count = fields.Integer(string='Number of Units', compute='_compute_unit_count', store=True)

    @api.depends('total_weight', 'weight_unit', 'weight_per_unit')
    def _compute_unit_count(self):
        for rec in self:
            weight_kg = rec.total_weight * 1000 if rec.weight_unit == 'ton' else rec.total_weight
            rec.unit_count = int(weight_kg / rec.weight_per_unit) if rec.weight_per_unit else 0