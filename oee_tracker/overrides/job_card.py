"""doc_events for the standard ERPNext Job Card: tell open Shop Floor screens to refresh."""

import frappe

from oee_tracker.overrides.downtime_entry import REALTIME_EVENT


def notify_shopfloor(doc, method=None):
	frappe.publish_realtime(
		REALTIME_EVENT,
		{"job_card": doc.name, "workstation": doc.workstation, "status": doc.status},
		after_commit=True,
	)
