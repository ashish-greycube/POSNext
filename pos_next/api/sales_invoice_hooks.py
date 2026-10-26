# Copyright (c) 2025, BrainWise and contributors
# For license information, please see license.txt

"""
Sales Invoice Hooks
Event handlers for Sales Invoice document events
"""

from decimal import Decimal, ROUND_FLOOR

import frappe
from frappe import _
from frappe.model.meta import get_field_precision
from frappe.utils import cint, flt


def validate(doc, method=None):
	"""
	Validate hook for Sales Invoice.
	Apply tax inclusive settings based on POS Profile configuration.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	apply_tax_inclusive(doc)


def before_submit(doc, method=None):
	"""Prepare POSNext payment amounts for ERPNext GL posting."""
	allocate_payment_base_amounts(doc)


def allocate_payment_base_amounts(doc):
	"""Allocate the rounded company-currency total across POS payment rows."""
	if not (
		cint(doc.get("is_pos"))
		and doc.get("posa_pos_opening_shift")
		and not cint(doc.get("is_return"))
	):
		return

	payments = [row for row in doc.get("payments", []) if flt(row.amount) > 0]
	if not payments:
		return

	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	precision = get_field_precision(
		frappe.get_meta("GL Entry").get_field("debit"),
		currency=company_currency,
	)

	unit_scale = Decimal(10) ** precision
	conversion_rate = Decimal(str(flt(doc.conversion_rate)))
	exact_units = [
		Decimal(str(flt(row.amount))) * conversion_rate * unit_scale
		for row in payments
	]
	target_base_amount = flt(
		sum(flt(row.amount) for row in payments) * flt(doc.conversion_rate),
		precision,
	)
	target_units = int(Decimal(str(target_base_amount)) * unit_scale)
	rounded_base_total = flt(
		sum(flt(row.base_amount, precision) for row in payments),
		precision,
	)

	if all(flt(row.base_amount, precision) for row in payments) and rounded_base_total == target_base_amount:
		return

	if target_units < len(payments):
		frappe.throw(
			_(
				"The payment split is too small to post in {0} at {1}-decimal currency precision. "
				"Combine payment rows or increase Currency Precision in System Settings."
			).format(company_currency, precision),
			title=_("Payment Amount Below Ledger Precision"),
		)

	allocated_units = [
		max(1, int(value.to_integral_value(rounding=ROUND_FLOOR)))
		for value in exact_units
	]
	remaining_units = target_units - sum(allocated_units)

	if remaining_units < 0:
		frappe.throw(
			_(
				"The payment split cannot be represented in {0} at {1}-decimal currency precision. "
				"Combine payment rows or increase Currency Precision in System Settings."
			).format(company_currency, precision),
			title=_("Payment Rounding Conflict"),
		)

	remainders = [
		value - value.to_integral_value(rounding=ROUND_FLOOR)
		for value in exact_units
	]
	for index in sorted(range(len(payments)), key=lambda i: remainders[i], reverse=True):
		if not remaining_units:
			break
		allocated_units[index] += 1
		remaining_units -= 1

	for row, units in zip(payments, allocated_units, strict=True):
		row.base_amount = flt(Decimal(units) / unit_scale, precision)

	doc.base_paid_amount = flt(sum(row.base_amount for row in payments), precision)


def apply_tax_inclusive(doc):
	"""
	Mark taxes as inclusive based on POS Profile setting.

	This function reads the tax_inclusive setting from POS Settings
	and applies it to all taxes in the invoice (except Actual charge type).

	Args:
		doc: Sales Invoice document
	"""
	if not doc.pos_profile:
		return

	try:
		# Get POS Settings for this profile
		pos_settings = frappe.db.get_value(
			"POS Settings",
			{"pos_profile": doc.pos_profile},
			["tax_inclusive"],
			as_dict=True
		)
		tax_inclusive = pos_settings.get("tax_inclusive", 0) if pos_settings else 0
	except Exception:
		tax_inclusive = 0

	has_changes = False
	for tax in doc.get("taxes", []):
		# Skip Actual charge type - these can't be inclusive
		if tax.charge_type == "Actual":
			if tax.included_in_print_rate:
				tax.included_in_print_rate = 0
				has_changes = True
			continue

		# Apply tax inclusive setting
		if tax_inclusive and not tax.included_in_print_rate:
			tax.included_in_print_rate = 1
			has_changes = True
		elif not tax_inclusive and tax.included_in_print_rate:
			tax.included_in_print_rate = 0
			has_changes = True

	# Recalculate if we made changes
	if has_changes:
		doc.calculate_taxes_and_totals()


def before_cancel(doc, method=None):
	"""
	Before Cancel hook for Sales Invoice.
	Cancel any credit redemption journal entries.

	Args:
		doc: Sales Invoice document
		method: Hook method name (unused)
	"""
	try:
		from pos_next.api.credit_sales import cancel_credit_journal_entries
		cancel_credit_journal_entries(doc.name)
	except Exception as e:
		frappe.log_error(
			title="Credit Sale JE Cancellation Error",
			message=f"Invoice: {doc.name}, Error: {str(e)}\n{frappe.get_traceback()}"
		)
		# Don't block invoice cancellation if JE cancellation fails
		frappe.msgprint(
			_("Warning: Some credit journal entries may not have been cancelled. Please check manually."),
			alert=True,
			indicator="orange"
		)
