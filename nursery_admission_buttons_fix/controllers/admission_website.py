from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

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
        _logger.info("Form POST received: %s", post)

        try:
            stage = request.env['nursery.admission.stage'].sudo().search([('name', '=', 'Submitted')], limit=1)
            parent_id = post.get('parent_id')

            admission = request.env['nursery.admission'].sudo().create({
                'child_name': post.get('child_name'),
                'birth_date': post.get('birth_date'),
                'gender': post.get('gender'),
                'reason_for_applying': post.get('reason_for_applying'),
                'parent_id': int(parent_id) if parent_id and parent_id.isdigit() else False,
                'stage_id': stage.id if stage else False,
            })

            _logger.info("Admission created with ID: %s", admission.id)

        except Exception as e:
            _logger.error("Error submitting admission form: %s", e)
            return request.render('website.500', {'error': str(e)})

        return request.redirect('/nursery/thankyou')

    @http.route('/nursery/thankyou', type='http', auth='public', website=True)
    def admission_thank_you(self, **kwargs):
        return request.render('nursery_admission_buttons_fix.admission_thankyou')
