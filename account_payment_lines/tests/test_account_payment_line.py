# Copyright 2022 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo.tests.common import TransactionCase


class TestAccountPaymentLines(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    # TODO: These cases and variants combined
    # Customer
    # Customer Refund
    # Supplier
    # Supplier Refund
    # Partial Payments
    # Multi-Currency
    # Analytic
