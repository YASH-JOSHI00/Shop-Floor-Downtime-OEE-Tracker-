"""Create a Downtime Reason for every standard stop_reason in use and back-fill old entries."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from oee_tracker.setup.custom_fields import get_custom_fields

# Category for a legacy Select value that has no default Downtime Reason mapped to it
LEGACY_CATEGORY = {
	"Excessive machine set up time": "Setup",
	"Unplanned machine maintenance": "Breakdown",
	"On-machine press checks": "Quality",
	"Machine operator errors": "Manpower",
	"Machine malfunction": "Breakdown",
	"Electricity down": "Power",
	"Other": "Other",
}


def execute():
	# post_model_sync patches run before after_migrate, so the custom fields may not exist yet
	create_custom_fields(get_custom_fields(), ignore_validate=True)

	from oee_tracker.install import create_default_reasons

	create_default_reasons()
	backfill()


def backfill():
	entry = frappe.qb.DocType("Downtime Entry")
	pending = (
		frappe.qb.from_(entry)
		.select(entry.stop_reason)
		.distinct()
		.where(entry.downtime_reason.isnull() | (entry.downtime_reason == ""))
		.run(pluck=True)
	)

	for stop_reason in pending:
		reason = get_or_create_reason(stop_reason or "Other")
		category, is_planned = frappe.db.get_value("Downtime Reason", reason, ["category", "is_planned"])
		condition = entry.stop_reason.isnull() if not stop_reason else entry.stop_reason == stop_reason
		(
			frappe.qb.update(entry)
			.set(entry.downtime_reason, reason)
			.set(entry.category, category)
			.set(entry.is_planned, is_planned)
			.where(condition & (entry.downtime_reason.isnull() | (entry.downtime_reason == "")))
			.run()
		)

	# Every historical entry has a To Time, so it is closed
	(
		frappe.qb.update(entry)
		.set(entry.status, "Closed")
		.where((entry.status.isnull() | (entry.status == "")) & entry.to_time.isnotnull())
		.run()
	)


def get_or_create_reason(stop_reason: str) -> str:
	if frappe.db.exists("Downtime Reason", stop_reason):
		return stop_reason
	existing = frappe.db.get_value(
		"Downtime Reason", {"legacy_stop_reason": stop_reason}, "name", order_by="creation asc"
	)
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Downtime Reason",
				"reason_name": stop_reason,
				"category": LEGACY_CATEGORY.get(stop_reason, "Other"),
				"legacy_stop_reason": stop_reason if stop_reason in LEGACY_CATEGORY else "Other",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
