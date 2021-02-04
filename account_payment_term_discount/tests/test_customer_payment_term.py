# Copyright 2018 Open Source Integrators (http://www.opensourceintegrators.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from dateutil.relativedelta import relativedelta

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DF
from odoo.tests import common
from odoo import fields


class TestLandedCostCompanyPercentage(common.TransactionCase):

    def setUp(self):
        super(TestLandedCostCompanyPercentage, self).setUp()

        # Refs
        self.main_company = self.env.ref('base.main_company')
        self.partner_id = self.env.ref('base.res_partner_4')
        self.journalrec = \
        self.env['account.journal'].search([('type', '=', 'sale')])[0]
        res_users_account_manager = self.env.ref(
            'account.group_account_manager')
        partner_manager = self.env.ref('base.group_partner_manager')
        account_user_type_expenses = self.env.ref(
            'account.data_account_type_expenses')
        account_user_type_receivable = self.env.ref(
            'account.data_account_type_receivable')
        self.payment_method = self.env.ref(
            'account.account_payment_method_manual_in')

        # Get required Model
        self.account_invoice_model = self.env['account.move']
        self.account_model = self.env['account.account']
        self.payment_term_model = self.env['account.payment.term']
        self.user_model = self.env['res.users']
        self.payment_model = self.env['account.payment']

        # Create users
        self.account_manager = self.user_model.with_context(
            {'no_reset_password': True}).create(
            dict(name="Adviser", company_id=self.main_company.id,
                 login="fm_adviser", email="accountmanager@yourcompany.com",
                 groups_id=[(6, 0, [res_users_account_manager.id,
                                    partner_manager.id])]))

        # Create expense account for discount
        self.account_discount_id = self.account_model.with_user(
            self.account_manager.id).create(
            dict(code="cust_acc_discount", name="Discount Expenses",
                 user_type_id=account_user_type_expenses.id, reconcile=True))

        # Create receivable account
        self.account_rec1_id = self.account_model.with_user(
            self.account_manager.id).create(
            dict(code="cust_acc_rec", name="Customer invoice receivable",
                 user_type_id=account_user_type_receivable.id, reconcile=True))

        # Prepare invoice line values
        self.invoice_line_data = [(0, 0, {
            'product_id': self.env.ref('product.product_product_5').id,
            'quantity': 10.0, 'account_id': self.env['account.account'].search(
                [('user_type_id', '=',
                  self.env.ref('account.data_account_type_revenue').id)],
                limit=1).id, 'name': 'product test 5', 'price_unit': 100.00})]

        # Create Payment term
        self.payment_term = self.payment_term_model.with_user(self.account_manager.id).create(
            dict(name="5%10 NET30", is_discount=True,
                 note="5% discount if payment done within 10days, "
                      "otherwise net",
                 line_ids=[(0, 0, {'value': 'balance', 'discount': 5.0,
                                   'discount_days': 10,
                                   'discount_expense_account_id':
                                       self.account_discount_id.id,
                                   'days': 10})]))

    def test_customer_invoice_payment_term_discount(self):
        """Test customer invoice and payment term discount"""

        # Create customer invoice and verify workflow with discount
        self.customer_invoice = self.account_invoice_model.with_user(
            self.account_manager.id).create(
            dict(name="Test Customer Invoice", reference_type="none",
                 payment_term_id=self.payment_term.id,
                 journal_id=self.journalrec.id, partner_id=self.partner_id.id,
                 account_id=self.account_rec1_id.id,
                 invoice_line_ids=self.invoice_line_data))
        self.assertEquals(self.customer_invoice.state, 'draft')
        # Validate customer invoice
        self.customer_invoice.action_invoice_open()
        self.assertEquals(self.customer_invoice.state, 'open')
        # Update payment date that's match with condition within 10 days
        invoice_date = fields.Date.from_string(
            self.customer_invoice.date_invoice)
        payment_date =  invoice_date + relativedelta(days=9)
        # Create customer payment
        payment_vals = {
            'invoice_ids': [(6, 0, [self.customer_invoice.id])],
            'invoice_id': self.customer_invoice.id,
            'amount': 950.0,
            'payment_date': payment_date,
            'communication': self.customer_invoice.number,
            'partner_id': self.partner_id.id,
            'partner_type': 'customer',
            'journal_id': self.journalrec.id,
            'payment_type': 'inbound',
            'payment_method_id': self.payment_method.id,
        }
        payment = self.payment_model.create(payment_vals)
        payment.onchange_payment_amount()
        payment.post()
        # Verify that invoice is now in Paid state
        self.assertEquals(self.customer_invoice.state, 'paid')

        # Create customer invoice and verify workflow without discount
        self.customer_invoice2 = self.account_invoice_model.with_user(
            self.account_manager.id).create(
            dict(name="Test Customer Invoice", reference_type="none",
                 payment_term_id=self.payment_term.id,
                 journal_id=self.journalrec.id, partner_id=self.partner_id.id,
                 account_id=self.account_rec1_id.id,
                 invoice_line_ids=self.invoice_line_data))
        self.assertEquals(self.customer_invoice2.state, 'draft')
        # Validate customer invoice
        self.customer_invoice2.action_invoice_open()
        self.assertEquals(self.customer_invoice2.state, 'open')
        # Update payment date after 15 days of invoice date
        invoice_date = fields.Date.from_string(
            self.customer_invoice2.date_invoice)
        payment_date =  invoice_date + relativedelta(days=15)
        # Create customer payment
        payment_vals = {
            'invoice_ids': [(6, 0, [self.customer_invoice2.id])],
            'invoice_id': self.customer_invoice2.id,
            'amount': 950.0,
            'payment_date': payment_date,
            'communication': self.customer_invoice2.number,
            'partner_id': self.partner_id.id,
            'partner_type': 'customer',
            'journal_id': self.journalrec.id,
            'payment_type': 'inbound',
            'payment_method_id': self.payment_method.id,
        }
        payment = self.payment_model.create(payment_vals)
        payment.onchange_payment_amount()
        payment.post()

        # Verify that invoice is still in Open state
        self.assertEqual(self.customer_invoice2.state, 'open')
