"""doc_events for the standard ERPNext Downtime Entry (wired in hooks.py; no controller override).

The standard Downtime Entry is not submittable, so the "close" logic runs in on_update when the
entry becomes Closed (To Time set) instead of on_submit.
"""

import frappe
from frappe import _
from frappe.model import no_value_fields
from frappe.utils import add_days, get_datetime, getdate, now_datetime, time_diff_in_seconds

from oee_tracker.shift import find_shift_window, get_next_boundary

SUPERVISOR_ROLES = ("Shopfloor Supervisor", "Manufacturing User", "Manufacturing Manager", "System Manager")
REALTIME_EVENT = "oee_workstation_status"


def validate(doc, method=None):
	doc.status = "Closed" if doc.to_time else "Open"
	validate_times(doc)
	validate_single_open_entry(doc)
	set_reason_details(doc)
	set_operator(doc)
	set_shift(doc)
	split_at_shift_boundary(doc)
	validate_maintenance_user_edit(doc)


def on_update(doc, method=None):
	if doc.flags.split_remainder_to:
		create_remainder(doc)

	before = doc.get_doc_before_save()
	for workstation in {doc.workstation, before and before.workstation}:
		if workstation:
			update_workstation_status(workstation)

	for job_card in {doc.job_card, before and before.job_card}:
		if job_card:
			update_job_card_downtime(job_card)

	queue_oee_rebuild(doc)


def on_trash(doc, method=None):
	if doc.workstation:
		update_workstation_status(doc.workstation, exclude=doc.name)
	if doc.job_card:
		update_job_card_downtime(doc.job_card, exclude=doc.name)
	queue_oee_rebuild(doc)


def validate_times(doc):
	if not doc.from_time:
		return
	if doc.status == "Open" and get_datetime(doc.from_time) > now_datetime():
		frappe.throw(_("From Time cannot be in the future for an open stop"))
	if doc.to_time:
		# The standard controller already checks order and recomputes; keep minutes consistent
		doc.downtime = time_diff_in_seconds(doc.to_time, doc.from_time) / 60


def validate_single_open_entry(doc):
	if doc.status != "Open" or not doc.workstation:
		return
	other = frappe.db.get_value(
		"Downtime Entry",
		{"workstation": doc.workstation, "status": "Open", "name": ("!=", doc.name or "")},
		"name",
	)
	if other:
		frappe.throw(
			_("Workstation {0} already has an open stop {1}. Close it before starting another.").format(
				frappe.bold(doc.workstation), frappe.get_desk_link("Downtime Entry", other)
			),
			title=_("Machine Already Stopped"),
		)


def set_reason_details(doc):
	if not doc.downtime_reason and doc.stop_reason:
		# Entries created by older integrations or data import that only set the standard Select
		doc.downtime_reason = frappe.db.exists("Downtime Reason", doc.stop_reason) or frappe.db.get_value(
			"Downtime Reason", {"legacy_stop_reason": doc.stop_reason, "disabled": 0}, "name"
		)
	if not doc.downtime_reason:
		return

	reason = frappe.get_cached_value(
		"Downtime Reason",
		doc.downtime_reason,
		["category", "is_planned", "legacy_stop_reason", "disabled"],
		as_dict=True,
	)
	if not reason:
		return
	if reason.disabled and doc.has_value_changed("downtime_reason"):
		frappe.throw(_("Downtime Reason {0} is disabled").format(frappe.bold(doc.downtime_reason)))
	doc.category = reason.category
	doc.is_planned = reason.is_planned
	doc.stop_reason = reason.legacy_stop_reason or "Other"


def set_shift(doc):
	if doc.shift or not (doc.workstation and doc.from_time):
		return

	window = find_shift_window(doc.workstation, doc.from_time)
	if window:
		doc.shift = window.shift


def set_operator(doc):
	if doc.operator:
		return
	doc.operator = frappe.db.get_value(
		"Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
	)


def split_at_shift_boundary(doc):
	"""A closed stop that crosses a shift change is cut at the boundary; on_update creates the rest."""
	if doc.status != "Closed" or not doc.workstation or doc.flags.skip_shift_split:
		return
	boundary = get_next_boundary(doc.workstation, doc.from_time, doc.to_time)
	if not boundary:
		return
	doc.flags.split_remainder_to = get_datetime(doc.to_time)
	doc.to_time = boundary
	doc.downtime = time_diff_in_seconds(doc.to_time, doc.from_time) / 60
	# The shift may have been set from the original from_time already; keep it


def create_remainder(doc):
	remainder = frappe.copy_doc(doc)
	remainder.from_time = doc.to_time
	remainder.to_time = doc.flags.split_remainder_to
	remainder.shift = None
	remainder.alert_sent = doc.alert_sent
	remainder.remarks = "\n".join(
		filter(None, [doc.remarks, _("Continued from {0} (split at shift change)").format(doc.name)])
	)
	doc.flags.split_remainder_to = None
	remainder.insert(ignore_permissions=True)
	frappe.msgprint(
		_("The stop crossed a shift change, so it was split. The rest is in {0}.").format(
			frappe.get_desk_link("Downtime Entry", remainder.name)
		),
		alert=True,
	)


def validate_maintenance_user_edit(doc):
	"""Maintenance Users may only add remarks to Breakdown entries."""
	if doc.flags.ignore_permissions or doc.is_new():
		return
	roles = frappe.get_roles()
	if "Maintenance User" not in roles or any(role in roles for role in SUPERVISOR_ROLES):
		return

	before = doc.get_doc_before_save()
	if ((before and before.category) or doc.category) != "Breakdown":
		frappe.throw(_("Maintenance Users can only update Breakdown entries"), frappe.PermissionError)

	if not before:
		return
	for df in doc.meta.fields:
		if df.fieldtype in no_value_fields or df.fieldname in ("remarks", "downtime", "status"):
			continue
		if str(doc.get(df.fieldname) or "") != str(before.get(df.fieldname) or ""):
			frappe.throw(
				_("Maintenance Users can only change Remarks (tried to change {0})").format(_(df.label)),
				frappe.PermissionError,
			)


def update_workstation_status(workstation: str, exclude: str | None = None):
	filters = {"workstation": workstation, "status": "Open"}
	if exclude:
		filters["name"] = ("!=", exclude)
	open_entry = frappe.db.get_value(
		"Downtime Entry", filters, ["name", "from_time", "downtime_reason"], as_dict=True
	)
	status = "Stopped" if open_entry else "Running"

	if frappe.db.get_value("Workstation", workstation, "current_status") != status:
		frappe.db.set_value("Workstation", workstation, "current_status", status, update_modified=False)

	frappe.publish_realtime(
		REALTIME_EVENT,
		{
			"workstation": workstation,
			"status": status,
			"downtime_entry": open_entry and open_entry.name,
			"from_time": open_entry and str(open_entry.from_time),
			"downtime_reason": open_entry and open_entry.downtime_reason,
		},
		after_commit=True,
	)


def update_job_card_downtime(job_card: str, exclude: str | None = None):
	entry = frappe.qb.DocType("Downtime Entry")
	query = (
		frappe.qb.from_(entry)
		.select(frappe.query_builder.functions.Sum(entry.downtime))
		.where((entry.job_card == job_card) & (entry.status == "Closed"))
	)
	if exclude:
		query = query.where(entry.name != exclude)
	total = query.run()[0][0] or 0
	frappe.db.set_value("Job Card", job_card, "downtime_minutes", total, update_modified=False)


def queue_oee_rebuild(doc):
	"""An entry edited after its day's OEE Logs were built makes those logs stale: refresh them.

	Only days that already have OEE Logs for this workstation are rebuilt. Days without logs are
	left to the daily job, otherwise logging a stop today would create empty "no production"
	logs for yesterday.
	"""
	if not (doc.workstation and doc.from_time):
		return
	before = doc.get_doc_before_save()
	times = [doc.from_time, doc.to_time]
	if before:
		times += [before.from_time, before.to_time]
	dates = [getdate(t) for t in times if t]
	# A stop just after midnight can belong to the previous day's night shift
	from_date, to_date = add_days(min(dates), -1), max(dates)

	posting_dates = frappe.get_all(
		"OEE Log",
		filters={"workstation": doc.workstation, "posting_date": ("between", [from_date, to_date])},
		pluck="posting_date",
		distinct=True,
		order_by="posting_date asc",
	)
	if not posting_dates:
		return

	frappe.enqueue(
		"oee_tracker.oee.build_for_dates",
		queue="long",
		dates=[str(d) for d in posting_dates],
		workstations=[doc.workstation],
		enqueue_after_commit=True,
		job_id=f"oee_rebuild::{doc.workstation}::{posting_dates[0]}::{posting_dates[-1]}",
		deduplicate=True,
	)
