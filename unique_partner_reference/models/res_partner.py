from odoo import models, api, _
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.constrains('ref', 'company_id')
    def _check_unique_ref_per_company(self):
        for partner in self:
            if not partner.ref :
                continue

            duplicate = self.env['res.partner'].search([
                ('ref', '=', partner.ref),
                ('company_id', 'in', [partner.company_id.id, False]),

            ]) - self #

            print(duplicate)

            if len(duplicate) >= 1:
                raise ValidationError(_(
                    "Reference '%s' already exists in company '%s' in the contact named '%s'."
                ) % (partner.ref, partner.company_id.name, duplicate.display_name))
    # @api.constrains('ref', 'company_id')
    # def _check_unique_ref_within_company_or_blank(self):
    #     for partner in self:
    #         if not partner.ref:
    #             continue
    #
    #         domain = [
    #             ('ref', '=', partner.ref),
    #             ('id', '!=', partner.id),
    #         ]
    #
    #         if partner.company_id:
    #             # Check for duplicates in the same company
    #             domain.append(('company_id', '=', partner.company_id.id))
    #         else:
    #             # Check for duplicates where company_id is blank
    #             domain.append(('company_id', '=', False))
    #
    #         duplicate = self.env['res.partner'].search(domain, limit=1)
    #
    #         if duplicate:
    #             raise ValidationError(_(
    #                 "Reference '%s' is already used in the same company or among contacts with no company set. (Contact: %s)"
    #             ) % (partner.ref, duplicate.display_name))

    # @api.constrains('ref', 'company_id')
    # def _check_unique_ref_per_company(self):
    #     for partner in self:
    #         if not partner.ref or not partner.company_id:
    #             continue
    #
    #         duplicate = self.env['res.partner'].search([
    #             ('ref', '=', partner.ref),
    #             ('company_id', '=',  self.env.user.company_id.id),
    #             ('id', '!=', partner.id)
    #         ], limit=1)
    #
    #         if duplicate:
    #             raise ValidationError(_(
    #                 "Reference '%s' already exists in company '%s' in the contact named '%s'."
    #             ) % (partner.ref, partner.company_id.name, duplicate.display_name))

    # @api.constrains('company_id')
    # def _check_company_required(self):
    #     for rec in self:
    #         if not rec.company_id:
    #             raise ValidationError(_("Please set the company before saving the contact."))
# from odoo import models, api, _
# from odoo.exceptions import ValidationError
#
# class ResPartner(models.Model):
#     _inherit = 'res.partner'
#
#     @api.constrains('ref', 'company_id')
#     def _check_unique_ref_for_basel_company(self):
#         for partner in self:
#             if not partner.ref or not partner.company_id:
#                 continue
#
#             # Only apply this constraint in Bassel's company
#             if partner.company_id.name == "Bassel's company":
#                 duplicate = self.env['res.partner'].search([
#                     ('ref', '=', partner.ref),
#                     ('company_id', '=', partner.company_id.id),
#                     ('id', '!=', partner.id)
#                 ], limit=1)
#
#                 if duplicate:
#                     raise ValidationError(_("Reference '%s' already exists in Bassel's company.") % partner.ref)
#
#     @api.constrains('company_id')
#     def _check_company_required(self):
#         for rec in self:
#             if not rec.company_id:
#                 raise ValidationError(_("Please set the company before saving the contact."))

# from odoo import models, api, _
# from odoo.exceptions import ValidationError
#
# class ResPartner(models.Model):
#     _inherit = 'res.partner'
#
#     @api.constrains('ref', 'company_id')
#     def _check_unique_ref_for_basel_company(self):
#         for partner in self:
#             if not partner.ref or not partner.company_id:
#                 continue
#
#             # Only apply this constraint in Bassel's company
#             if partner.company_id.name == "Bassel's company":
#                 duplicate = self.env['res.partner'].search([
#                     ('ref', '=', partner.ref),
#                     ('company_id', '=', partner.company_id.id),
#                     ('id', '!=', partner.id)
#                 ], limit=1)
#
#                 if duplicate:
#                     raise ValidationError(_("Reference '%s' already exists in Bassel's company.") % partner.ref)






# This SQL constraint and will not work per company

    #
    # @api.constrains('ref')
    # def _check_ref_unique(self):
    #     for partner in self:
    #         if partner.ref:
    #             duplicates = self.env['res.partner'].search_count([
    #                 ('ref', '=', partner.ref),
    #                 ('id', '!=', partner.id)
    #             ])
    #             if duplicates > 0:
    #                 raise ValidationError('Reference field must be unique.')
    #
    #
    # @api.returns('self', lambda value: value.id)
    # def copy(self, default=None):
    #     default = default or {}
    #     default['ref'] = False
    #     return super().copy(default=default)