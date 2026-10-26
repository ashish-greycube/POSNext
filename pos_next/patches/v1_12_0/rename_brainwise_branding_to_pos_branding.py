import frappe


OLD_DOCTYPE = "BrainWise Branding"
NEW_DOCTYPE = "POS Branding"


def execute():
	"""Rename the branding Single DocType while preserving its stored values."""
	if not frappe.db.exists("DocType", OLD_DOCTYPE):
		return

	if frappe.db.exists("DocType", NEW_DOCTYPE):
		return

	frappe.rename_doc(
		"DocType",
		OLD_DOCTYPE,
		NEW_DOCTYPE,
		force=True,
	)
