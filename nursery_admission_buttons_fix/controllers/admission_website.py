from odoo import http
from odoo.http import request

class AdmissionWebsite(http.Controller):

    @http.route('/nursery/apply', type='http', auth='public', website=True)
    def admission_form(self, **kwargs):
        parents = request.env['res.partner'].sudo().search([('is_company', '=', False), ('email', '!=', False)])
        return request.render('nursery_admission_buttons_fix.admission_website_form', {
            'parents': parents,
        })

    @http.route('/nursery/submit', type='http', auth='public', website=True, methods=['POST'])
    def admission_submit(self, **post):
        request.env['nursery.admission'].sudo().create({
            'child_name': post.get('child_name'),
            'birth_date': post.get('birth_date'),
            'gender': post.get('gender'),
            'parent_id': int(post.get('parent_id')),
            'status': 'submitted',
        })
        return request.redirect('/nursery/thankyou')

    @http.route('/nursery/thankyou', type='http', auth='public', website=True)
    def admission_thank_you(self, **kwargs):
        return request.render('nursery_admission_buttons_fix.admission_thankyou')
