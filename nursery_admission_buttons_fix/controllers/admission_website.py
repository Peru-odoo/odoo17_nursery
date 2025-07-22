from odoo import http
from odoo.http import request

class AdmissionWebsite(http.Controller):

    @http.route('/nursery/apply', type='http', auth='public', website=True)
    def admission_form(self, **kwargs):
        parents = request.env['res.partner'].sudo().search([
            ('is_company', '=', False),
            ('email', '!=', False)
        ])
        return request.render('nursery_admission_buttons_fix.admission_website_form', {
            'parents': parents,
        })

    @http.route('/nursery/submit', type='http', auth='public', website=True, methods=['POST'])
    def admission_submit(self, **post):
        try:
            request.env['nursery.admission'].sudo().create({
                'child_name': post.get('child_name'),
                'birth_date': post.get('birth_date'),
                'gender': post.get('gender'),
                'reason_for_applying': post.get('reason_for_applying'),
                'parent_id': int(post.get('parent_id')),
                'status': 'submitted',
            })
        except Exception as e:
            return request.render('website.500', {'error': str(e)})

        return request.redirect('/nursery/thankyou')

    @http.route('/nursery/thankyou', type='http', auth='public', website=True)
    def admission_thank_you(self, **kwargs):
        return request.render('nursery_admission_buttons_fix.admission_thankyou')

    @http.route('/nursery/test', type='http', auth='public', website=True)
    def test_route(self, **kwargs):
        return "Test Route is Working"
