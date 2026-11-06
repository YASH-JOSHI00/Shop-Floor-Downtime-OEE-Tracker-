# Copyright (c) 2026, yashjoshi and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate


class OEESettings(Document):
	def validate(self):
		if (self.alert_threshold_minutes or 0) < 1:
			frappe.throw(_("Alert Threshold must be at least 1 minute"))
		if self.oee_target and not 0 < self.oee_target <= 100:
			frappe.throw(_("OEE Target must be between 0 and 100"))


@frappe.whitelist()
def rebuild_oee_logs(from_date: str, to_date: str):
	frappe.only_for(("System Manager", "Manufacturing Manager"))
	if not from_date or not to_date:
		frappe.throw(_("Set From Date and To Date"))
	if getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date"))
	if date_diff(to_date, from_date) > 366:
		frappe.throw(_("Rebuild at most one year at a time"))

	frappe.enqueue(
		"oee_tracker.oee.build_for_range",
		queue="long",
		timeout=3600,
		from_date=from_date,
		to_date=to_date,
		job_id=f"oee_rebuild::{from_date}::{to_date}",
		deduplicate=True,
	)
	return _("OEE Logs are being rebuilt in the background")
