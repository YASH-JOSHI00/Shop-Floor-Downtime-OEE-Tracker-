"""The app was first installed with modules.txt reading "oee tracker". v16's desk matches module
names case-sensitively, so the "Shop Floor" sidebar (module "OEE Tracker") was never resolved and
the desk showed "Page not found". Rename the Module Def to the exact-case name."""

import frappe

MODULE = "OEE Tracker"


def execute():
	module_def = frappe.qb.DocType("Module Def")
	(
		frappe.qb.update(module_def)
		.set(module_def.name, MODULE)
		.set(module_def.module_name, MODULE)
		.where((module_def.app_name == "oee_tracker") & (module_def.name == MODULE))
		.run()
	)
	frappe.clear_cache()
