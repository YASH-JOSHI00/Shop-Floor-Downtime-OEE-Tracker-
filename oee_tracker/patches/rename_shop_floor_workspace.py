"""The app's workspace and sidebar were renamed from "Shop Floor" to "OEE Tracker" to match the app
name. The new ones are synced from files; remove the old records left behind."""

import frappe


def execute():
	for doctype in ("Workspace", "Sidebar"):
		if frappe.db.exists(doctype, {"name": "Shop Floor", "module": "OEE Tracker"}):
			frappe.delete_doc(doctype, "Shop Floor", force=True, ignore_permissions=True)
