# Copyright 2022 ForgeFlow, S.L.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

dict_payment_type = dict(
    inbound=["out_invoice", "out_refund", "out_receipt"],
    outbound=["in_invoice", "in_refund", "in_receipt"],
)


class AccountPayment(models.Model):
    _inherit = "account.payment"

    line_payment_counterpart_ids = fields.One2many(
        "account.payment.counterpart.line",
        "payment_id",
        string="Counterpart Lines",
        readonly=True,
        states={"draft": [("readonly", False)]},
        help="Use these lines to add matching lines, for example in a credit"
        "card payment, financing interest or commission is added",
    )

    def _process_post_reconcile(self):
        for rec in self:
            for line in rec.line_payment_counterpart_ids:
                if line.aml_id:
                    to_reconcile = (line.aml_id + line.move_ids).filtered(
                        lambda x: not x.reconciled
                    )
                    if to_reconcile:
                        to_reconcile.reconcile()
        return True

    def _get_moves_domain(self):
        domain = [
            ("amount_residual", "!=", 0.0),
            ("state", "=", "posted"),
            ("company_id", "=", self.company_id.id),
            (
                "commercial_partner_id",
                "=",
                self.partner_id.commercial_partner_id.id,
            ),
        ]
        if self.partner_type == "supplier":
            if self.payment_type == "outbound":
                domain.append(("move_type", "in", ("in_invoice", "in_receipt")))
            if self.payment_type == "inbound":
                domain.append(("move_type", "=", "in_refund"))
        elif self.partner_type == "customer":
            if self.payment_type == "outbound":
                domain.append(("move_type", "=", "out_refund"))
            if self.payment_type == "inbound":
                domain.append(("move_type", "in", ("out_invoice", "out_receipt")))
        return domain

    def _filter_amls(self, amls):
        return amls.filtered(
            lambda x: x.partner_id.commercial_partner_id.id
            == self.partner_id.commercial_partner_id.id
            and x.amount_residual != 0
        )

    @api.onchange(
        "payment_type",
        "partner_type",
        "partner_id",
        "amount",
        "currency_id",
        "date",
    )
    def _onchange_info_lines(self):
        self.ensure_one()
        if self.is_internal_transfer:
            return {}
        else:
            move_model = self.env["account.move"]
            line_model = self.env["account.payment.counterpart.line"]
            for rec in self:
                if not rec.partner_id:
                    continue
                domain = self._get_moves_domain()
                pending_invoices = move_model.search(
                    domain, order="invoice_date_due ASC"
                )
                pending_amount = rec.amount
                lines_data = line_model.browse()
                for invoice in pending_invoices:
                    for aml in self._filter_amls(invoice.line_ids):
                        amount_to_apply = 0
                        amount_residual = rec.company_id.currency_id._convert(
                            aml.amount_residual,
                            rec.currency_id,
                            rec.company_id,
                            date=rec.date,
                        )
                        if pending_amount >= 0:
                            amount_to_apply = min(abs(amount_residual), pending_amount)
                            pending_amount -= abs(amount_residual)
                        lines_data |= line_model.new(
                            {
                                "name": "/",
                                "move_id": invoice.id,
                                "aml_id": aml.id,
                                "account_id": aml.account_id.id,
                                "partner_id": rec.partner_id.commercial_partner_id.id,
                                "amount": amount_to_apply,
                            }
                        )
                rec.line_payment_counterpart_ids = lines_data

    def action_delete_counterpart_lines(self):
        if self.line_payment_counterpart_ids and self.state == "draft":
            self.line_payment_counterpart_ids = [(5, 0, 0)]

    def _prepare_move_line_default_vals(self, write_off_line_vals=False):
        res = super(AccountPayment, self)._prepare_move_line_default_vals(
            write_off_line_vals
        )
        write_off_amount_currency = (
            write_off_line_vals and write_off_line_vals.get("amount", 0.0) or 0.0
        )
        if self.payment_type == "outbound":
            write_off_amount_currency *= -1
        write_off_balance = self.currency_id._convert(
            write_off_amount_currency,
            self.company_id.currency_id,
            self.company_id,
            self.date,
        )
        new_aml_lines = []
        for line in self.line_payment_counterpart_ids:
            line_balance = (
                line.amount if self.payment_type == "outbound" else line.amount * -1
            )
            line_balance_currency = (
                line.amount_currency
                if self.payment_type == "outbound"
                else line.amount_currency * -1
            )
            same_currency = line.payment_id.currency_id.id == (
                line.aml_id.move_id.currency_id.id or line.move_id.currency_id.id
            ) or (not line.aml_id and not line.move_id)
            aml_value = line_balance_currency + write_off_balance
            aml_value_currency = line_balance + write_off_amount_currency
            new_aml_lines.append(
                {
                    "name": line.display_name,
                    "debit": aml_value > 0.0 and aml_value or 0.0,
                    "credit": aml_value < 0.0 and -aml_value or 0.0,
                    "amount_currency": not same_currency
                    and aml_value
                    or aml_value_currency,
                    "date_maturity": self.date,
                    "partner_id": line.partner_id.commercial_partner_id.id,
                    "account_id": line.account_id.id,
                    "currency_id": line.payment_id.currency_id.id,
                    "payment_id": self.id,
                    "payment_line_id": line.id,
                    "analytic_account_id": line.analytic_account_id.id,
                    "analytic_tag_ids": line.analytic_tag_ids
                    and [(6, 0, line.analytic_tag_ids.ids)]
                    or [],
                }
            )
        if len(res) >= 2:
            res.pop(1)
            res += new_aml_lines
        return res

    def action_post(self):
        for rec in self.filtered(
            lambda x: x.line_payment_counterpart_ids and not x.move_id.line_ids
        ):
            rec.move_id.line_ids = [
                (0, 0, line_vals) for line_vals in rec._prepare_move_line_default_vals()
            ]
        res = super(AccountPayment, self).action_post()
        self._process_post_reconcile()
        return res

    def action_draft(self):
        res = super().action_draft()
        for rec in self.filtered(lambda x: x.line_payment_counterpart_ids):
            # CHECK ME: force to recreate lines
            # if document back to draft state,
            # because we can change counterpart lines,
            # but change will not be propagated properly
            rec.move_id.line_ids.unlink()
        return res


class AccountPaymentCounterLines(models.Model):
    _name = "account.payment.counterpart.line"
    _description = "Counterpart line payment"

    payment_id = fields.Many2one(
        "account.payment", string="Payment", required=False, ondelete="cascade"
    )
    company_id = fields.Many2one(related="payment_id.company_id")
    name = fields.Char(string="Description", required=True, default="/")
    account_id = fields.Many2one(
        "account.account",
        string="Account",
        required=True,
        ondelete="restrict",
        check_company=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Analytic Account",
        ondelete="restrict",
        check_company=True,
    )
    analytic_tag_ids = fields.Many2many(
        "account.analytic.tag",
        string="Analytic Tags",
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency", string="Currency", related="payment_id.currency_id"
    )
    amount = fields.Monetary(string="Amount", required=True)
    amount_currency = fields.Monetary(
        string="Amount in Company Currency", compute="_compute_amounts"
    )
    aml_amount_residual = fields.Monetary(
        string="Amount Residual",
        compute="_compute_amounts",
    )
    residual_after_payment = fields.Monetary(
        compute="_compute_amounts",
    )
    aml_amount_residual_currency = fields.Monetary(
        string="Amount Residual Currency",
        compute="_compute_amounts",
    )
    residual_after_payment_currency = fields.Monetary(
        compute="_compute_amounts",
    )

    @api.depends(
        "aml_id.amount_residual", "amount", "payment_id.currency_id", "payment_id.date"
    )
    def _compute_amounts(self):
        for rec in self:
            rec.amount_currency = rec.payment_id.currency_id._convert(
                rec.amount,
                rec.payment_id.company_id.currency_id,
                rec.payment_id.company_id,
                date=rec.payment_id.date,
            )
            rec.aml_amount_residual = rec.aml_id.amount_residual
            rec.residual_after_payment = (
                abs(rec.aml_id.amount_residual) - rec.amount_currency
            )
            rec.aml_amount_residual_currency = rec.aml_id.amount_residual_currency
            rec.residual_after_payment_currency = (
                abs(rec.aml_id.amount_residual_currency) - rec.amount_currency
            )

    partner_id = fields.Many2one("res.partner", string="Partner", ondelete="restrict")
    commercial_partner_id = fields.Many2one(related="partner_id.commercial_partner_id")
    move_id = fields.Many2one(
        "account.move", string="Journal Entry", ondelete="set null"
    )
    move_ids = fields.One2many(
        "account.move.line",
        "payment_line_id",
        string="Journal Entries Created",
    )
    aml_id = fields.Many2one(
        "account.move.line", string="Journal Item to Reconcile", ondelete="set null"
    )
    aml_date_maturity = fields.Date(
        string="Date Maturity", required=False, related="aml_id.date_maturity"
    )

    @api.onchange("move_id", "aml_id")
    def _onchange_move_id(self):
        aml_model = self.env["account.move.line"]
        for rec in self:
            type_move = dict_payment_type.get(rec.payment_id.payment_type, [])
            if rec.move_id and not rec.aml_id:
                domain = [
                    ("move_id", "=", rec.move_id.id),
                    ("amount_residual", "!=", 0.0),
                ]
                lines_ordered = aml_model.search(
                    domain, order="date_maturity ASC", limit=1
                )
                if lines_ordered:
                    rec.aml_id = lines_ordered.id
            if rec.aml_id:
                rec.move_id = rec.aml_id.move_id.id
                rec.account_id = rec.aml_id.account_id.id
                rec.amount = abs(rec.aml_id.amount_residual)
                rec.partner_id = rec.aml_id.partner_id.id
                if rec.move_id.move_type == "entry":
                    if rec.payment_id.partner_type == "supplier":
                        if rec.payment_id.payment_type == "outbound":
                            rec.amount = -rec.aml_id.amount_residual
                        else:
                            rec.amount = rec.aml_id.amount_residual
                    else:
                        if rec.payment_id.payment_type == "outbound":
                            rec.amount = -rec.aml_id.amount_residual
                        else:
                            rec.amount = rec.aml_id.amount_residual
                else:
                    if (
                        type_move
                        and rec.move_id.move_type not in type_move
                        and rec.amount
                    ):
                        rec.amount *= -1

    @api.constrains("amount", "aml_amount_residual")
    def constrains_amount_residual(self):
        for rec in self:
            if rec.aml_id and 0 < rec.aml_amount_residual < rec.amount:
                raise ValidationError(
                    _(
                        "the amount exceeds the residual amount, please check the invoice %s"
                    ),
                    (rec.aml_id.move_id.name or rec.aml_id.name),
                )
