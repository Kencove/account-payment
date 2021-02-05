# Copyright (C) 2021, Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Payment Batch Processing",
    "version": "14.0.1.0.0",
    "license": "AGPL-3",
    "author": "Open Source Integrators, Odoo Community Association (OCA)",
    "summary": """
        Account Batch Payments Processing for Customers Invoices and
        Supplier Invoices
    """,
    "category": "Extra",
    "maintainer": "Open Source Integrators",
    "website": "https://github.com/OCA/account-payment",
    "depends": [
        "account",
        "account_check_printing",
        "account_batch_payment",
        "account_payment_order",
    ],
    "data": [
        "security/ir.model.access.csv",
        "wizard/invoice_batch_process_view.xml",
        "views/invoice_view.xml",
    ],
    "external_dependencies": {
        "python": ["num2words"],
    },
    "installable": True,
}
