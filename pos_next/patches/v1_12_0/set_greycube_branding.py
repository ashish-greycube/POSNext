import frappe


DOCTYPE = "POS Branding"
BRAND_NAME = "Greycube Technologies"
BRAND_URL = "https://greycube.in"
LEGACY_BRAND_NAMES = {None, "", "BrainWise"}
LEGACY_BRAND_URLS = {None, "", "https://nexus.brainwise.me"}


def execute():
	"""Replace legacy storefront branding without overwriting custom brands."""
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	doc = frappe.get_single(DOCTYPE)
	changed = False

	if doc.brand_name in LEGACY_BRAND_NAMES:
		doc.brand_name = BRAND_NAME
		changed = True

	if doc.brand_url in LEGACY_BRAND_URLS:
		doc.brand_url = BRAND_URL
		changed = True

	if not changed and doc.encrypted_signature:
		return

	# This controlled migration intentionally bypasses the interactive master key.
	doc.before_save()
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)
