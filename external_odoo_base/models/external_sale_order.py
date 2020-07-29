# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
from odoo import api, fields, models, _

from dateutil.relativedelta import relativedelta
from datetime import datetime
_logger = logging.getLogger(__name__)


class ExternalSaleOrder(models.Model):
    _name = 'external.sale.order'
    _description = 'External Sale Order'
    _order = 'create_date desc'
    _rec_name = 'external_id'

    external_url = fields.Char(        
        compute='_compute_external_url',
        string='External Url',
        store=False
    )

    @api.multi
    @api.depends('external_source_id', 'external_id')
    def _compute_external_url(self):
        self.ensure_one()
        self.external_url = ''
        if self.external_source_id.type == 'shopify':
            self.external_url = 'https://%s/admin/orders/%s' % (
                self.external_source_id.url,
                self.external_id
            )
        elif self.external_source_id.type == 'woocommerce':
            self.external_url = '%swp-admin/post.php?post=%s&action=edit' % (
                self.external_source_id.url,
                self.external_id
            )
    # fields
    external_id = fields.Char(
        string='External Id'
    )
    external_billing_address_id = fields.Many2one(
        comodel_name='external.address',
        string='Billing Address'
    )
    external_shipping_address_id = fields.Many2one(
        comodel_name='external.address',
        string='Shipping Address'
    )
    external_customer_id = fields.Many2one(
        comodel_name='external.customer',
        string='Customer'
    )
    woocommerce_state = fields.Selection(
        [
            ('none', 'Ninguno'),
            ('pending', 'Pending Payment'),
            ('shipped', 'Shipped'),
            ('processing', 'Processing'),
            ('on-hold', 'On Hold'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
            ('refunded', 'Refunded'),
            ('failed', 'Failed')
        ],
        string='Woocommerce State',
        default='none'
    )
    shopify_state = fields.Selection(
        [
            ('none', 'Ninguno'),
            ('pending', 'Pending'),
            ('authorized', 'Authorized'),
            ('paid', 'Paid'),
            ('partially_paid', 'Partially Paid'),
            ('refunded', 'Refunded'),
            ('partially_refunded', 'Partially Refunded'),
            ('voided', 'Voided'),
        ],
        string='Shopify State',
        default='none'
    )
    date = fields.Datetime(
        string='Date'
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency'
    )
    external_source_id = fields.Many2one(
        comodel_name='external.source',
        string='Source'
    )
    external_source_type = fields.Char(
        compute='_compute_external_source_type',
        store=False,
        string='Source Type'
    )
    payment_transaction_id = fields.Many2one(
        comodel_name='payment.transaction',
        string='Payment Transaction'
    )
    lead_id = fields.Many2one(
        comodel_name='crm.lead',
        string='Lead'
    )
    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Pedido de venta'
    )
    number = fields.Integer(
        string='Number'
    )
    total_price = fields.Monetary(
        string='Total Price'
    )
    subtotal_price = fields.Monetary(
        string='Subtotal Price'
    )
    total_tax = fields.Monetary(
        string='Total Tax'
    )
    total_discounts = fields.Monetary(
        string='Total Discounts'
    )
    total_line_items_price = fields.Monetary(
        string='Total Line Items Price'
    )
    total_shipping_price = fields.Monetary(
        string='Total Shipping Price'
    )
    external_sale_order_discount_ids = fields.One2many(
        'external.sale.order.discount',
        'external_sale_order_id',
        string='Discounts',
        copy=True
    )
    external_sale_order_line_ids = fields.One2many(
        'external.sale.order.line',
        'external_sale_order_id',
        string='Lines',
        copy=True
    )
    external_sale_order_shipping_ids = fields.One2many(
        'external.sale.order.shipping',
        'external_sale_order_id',
        string='Shipping Lines',
        copy=True
    )
    # extra landing
    landing_url = fields.Char(
        string='Landing Url'
    )
    landing_utm_campaign = fields.Char(
        string='Landing Utm campaign'
    )
    landing_utm_medium = fields.Char(
        string='Landing Utm medium'
    )
    landing_utm_source = fields.Char(
        string='Landing Utm source'
    )

    @api.multi
    @api.depends('external_source_id')
    def _compute_external_source_type(self):
        self.ensure_one()
        self.external_source_type = self.external_source_id.type

    @api.multi
    def action_run_multi(self):
        if self.sale_order_id.id == 0:
            self.action_run()

    @api.multi
    def allow_create(self):
        self.ensure_one()
        return_item = False
        # operations
        if self.external_source_id:
            if self.external_source_id.type == 'woocommerce':
                if self.woocommerce_state in ['processing', 'shipped', 'completed']:
                    return_item = True
            elif self.external_source_id.type == 'shopify':
                if self.shopify_state == 'paid':
                    return_item = True
        # return
        return return_item

    @api.multi
    def action_run(self):
        self.ensure_one()
        # allow_create
        allow_create_item = self.allow_create()[0]
        if allow_create_item:
            # actions
            self.action_crm_lead_create()
            self.action_sale_order_create()
            self.action_sale_order_done()
            self.action_payment_transaction_create()
            self.action_crm_lead_win()
        # return
        return False

    @api.multi
    def action_crm_lead_create(self):
        self.ensure_one()
        if self.lead_id.id == 0:
            if self.external_customer_id:
                if self.external_customer_id.partner_id:
                    # date_deadline
                    current_date = datetime.today()
                    date_deadline = current_date + relativedelta(days=1)
                    # vals
                    crm_lead_vals = {
                        'external_sale_order_id': self.id,
                        'type': 'opportunity',
                        'name': "%s %s" % (
                            self.external_source_id.type,
                            self.number
                        ),
                        'team_id': 1,
                        'probability': 10,
                        'date_deadline':
                            str(date_deadline.strftime("%Y-%m-%d %H:%I:%S"))
                    }
                    # user_id
                    if self.external_source_id.external_sale_order_user_id:
                        crm_lead_vals['user_id'] = \
                            self.external_source_id.\
                                external_sale_order_user_id.id
                    # create
                    crm_lead_obj = self.env['crm.lead'].sudo(self.create_uid).create(crm_lead_vals)
                    # update_partner_id
                    crm_lead_obj.partner_id = self.external_customer_id.partner_id.id
                    crm_lead_obj._onchange_partner_id()
                    # user_id (partner_id)
                    if self.external_source_id.external_sale_order_user_id:
                        if crm_lead_obj.partner_id.user_id.id == 0:
                            crm_lead_obj.partner_id.user_id = \
                                self.external_source_id.external_sale_order_user_id.id
                    # lead_id
                    self.lead_id = crm_lead_obj.id
        # return
        return False

    @api.multi
    def action_sale_order_create(self):
        self.ensure_one()
        if self.sale_order_id.id == 0:
            # allow_create_sale_order
            allow_create_sale_order = False
            # external_customer_id
            if self.external_customer_id:
                if self.external_customer_id.partner_id:
                    # external_billing_address_id
                    if self.external_billing_address_id:
                        if self.external_billing_address_id.partner_id:
                            # external_shipping_address_id
                            if self.external_shipping_address_id:
                                if self.external_shipping_address_id.partner_id:
                                    allow_create_sale_order = True
                                    # external_sale_order_line_ids
                                    for line_id in self.external_sale_order_line_ids:
                                        if line_id.external_product_id.id == 0:
                                            allow_create_sale_order = False
            # operations
            if allow_create_sale_order:
                # vals
                vals = {
                    'external_sale_order_id': self.id,
                    'state': 'draft',
                    'opportunity_id': self.lead_id.id,
                    'team_id': self.lead_id.team_id.id,
                    'partner_id': self.lead_id.partner_id.id,
                    'partner_invoice_id':
                        self.external_billing_address_id.partner_id.id,
                    'partner_shipping_id':
                        self.external_shipping_address_id.partner_id.id,
                    'date_order': str(self.date),
                    'show_total': True,
                    'origin': str(self.lead_id.name)
                }
                # user_id
                if self.lead_id.user_id:
                    vals['user_id'] = self.lead_id.user_id.id
                # payment_mode_id
                if self.external_source_id.\
                        external_sale_order_account_payment_mode_id:
                    vals['payment_mode_id'] = \
                        self.external_source_id.\
                            external_sale_order_account_payment_mode_id.id
                # payment_term_id
                if self.external_source_id.\
                        external_sale_order_account_payment_term_id:
                    vals['payment_term_id'] = \
                        self.external_source_id.\
                            external_sale_order_account_payment_term_id.id
                # create
                obj = self.env['sale.order'].sudo(self.create_uid).create(vals)
                # define
                self.sale_order_id = obj.id
                # external_sale_order_shipping_id
                for line_id in self.external_sale_order_shipping_ids:
                    #data
                    line_vals = {
                        'order_id': self.sale_order_id.id,
                        'product_id':
                            self.external_source_id.
                                external_sale_order_shipping_product_template_id.id,
                        'name': str(line_id.title),
                        'product_uom_qty': 1,
                        'product_uom': 1,
                        'price_unit': line_id.unit_price_without_tax,
                        'discount': 0
                    }
                    # Fix product_uom
                    if self.external_source_id.\
                            external_sale_order_shipping_product_template_id.uom_id:
                        line_vals['product_uom'] = \
                            self.external_source_id.\
                                external_sale_order_shipping_product_template_id.uom_id.id
                    # create
                    obj = self.env['sale.order.line'].sudo(self.create_uid).create(line_vals)
                    # update
                    line_id.sale_order_line_id = obj.id
                # lines
                for line_id in self.external_sale_order_line_ids:
                    # data
                    line_vals = {
                        'order_id': self.sale_order_id.id,
                        'product_id':
                            line_id.external_product_id.product_template_id.id,
                        'name': str(line_id.title),
                        'product_uom_qty': external_sale_order_line_id.quantity,
                        'product_uom': 1,
                        'price_unit': line_id.unit_price_without_tax,
                        'discount': 0                
                    } 
                    # Fix product_uom
                    if line_id.external_product_id.product_template_id.uom_id:
                        line_vals['product_uom'] = \
                            line_id.external_product_id.product_template_id.uom_id.id
                    # create
                    obj = self.env['sale.order.line'].sudo(self.create_uid).create(line_vals)
                    # update
                    line_id.sale_order_line_id = obj.id
        # return
        return False
    
    @api.multi
    def action_sale_order_done_error_partner_id_without_vat(self):
        self.ensure_one()
        _logger.info(
            _('The order %s cannot be confirmed because the client does NOT have a CIF')
            % self.sale_order_id.name
        )

    @api.multi
    def action_sale_order_done(self):
        self.ensure_one()
        if self.sale_order_id:
            if self.sale_order_id.state in ['draft', 'sent']:
                if not self.sale_order_id.partner_id.vat:
                    self.action_sale_order_done_error_partner_id_without_vat()
                else:
                    self.sale_order_id.sudo(self.create_uid).action_confirm()
            
    @api.multi
    def action_payment_transaction_create_multi(self):
        self.ensure_one()
        if self.payment_transaction_id.id == 0:
            self.action_payment_transaction_create()
    
    @api.multi
    def action_payment_transaction_create(self):
        self.ensure_one()
        if self.payment_transaction_id.id == 0:
            if self.sale_order_id:
                if self.external_customer_id:
                    if self.external_customer_id.partner_id:
                        # payment_transaction
                        vals = {
                            'reference': self.sale_order_id.name,
                            'sale_order_id': self.sale_order_id.id,
                            'amount': self.total_price,
                            'currency_id': self.currency_id.id,
                            'partner_id': self.external_customer_id.partner_id.id,
                            'acquirer_id':
                                self.external_source_id.external_sale_payment_acquirer_id.id,
                            'date_validate': self.date,
                            'state': 'draft',
                        }
                        obj = self.env['payment.transaction'].sudo(self.create_uid).create(vals)
                        # write
                        obj.write({
                            'state': 'done'
                        })
                        # update
                        self.payment_transaction_id = obj.id
    
    @api.multi
    def action_crm_lead_win(self):
        self.ensure_one()
        if self.lead_id:
            if self.sale_order_id.state == 'sale':
                if self.lead_id.probability < 100:
                    self.lead_id.sudo(self.create_uid).action_set_won() 