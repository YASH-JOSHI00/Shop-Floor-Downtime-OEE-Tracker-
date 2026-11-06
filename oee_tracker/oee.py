"""OEE calculation and OEE Log building.

OEE = Availability x Performance x Quality, per workstation, per shift, per day.

	planned production time = shift minutes - breaks - planned downtime
	run time                = planned production time - unplanned downtime
	availability            = run time / planned production time
	performance             = ideal cycle time x total qty / run time
	quality                 = good qty / total qty
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime, today

from oee_tracker.shift import ShiftWindow, get_shift_windows_for_date, overlap_minutes

FLAG_NO_PRODUCTION = "No production recorded in this shift; Performance and Quality skipped."
FLAG_NO_CYCLE_TIME = "Ideal Cycle Time is not set on the Workstation; Performance skipped."
FLAG_OVER_100 = "Performance was {0}% (above 100%); check the Ideal Cycle Time on the Workstation."


def compute_oee(workstation: str, window: ShiftWindow, until: datetime | None = None) -> frappe._dict:
	"""OEE numbers for one shift instance. `until` clips the shift (live figures for today)."""
	end = min(window.end, until) if until else window.end
	start = window.start
	if end <= start:
		return frappe._dict(planned_time=0)

	breaks = [(max(b_s, start), min(b_e, end)) for b_s, b_e in window.breaks if b_s < end and b_e > start]
	shift_minutes = (end - start).total_seconds() / 60
	break_minutes = sum((b_e - b_s).total_seconds() / 60 for b_s, b_e in breaks)

	planned_downtime = unplanned_downtime = 0.0
	downtime_count = 0
	now = now_datetime()
	for entry in get_downtime_entries(workstation, start, end):
		entry_end = get_datetime(entry.to_time) if entry.to_time else now
		inside = overlap_minutes(get_datetime(entry.from_time), entry_end, start, end)
		in_breaks = sum(
			overlap_minutes(get_datetime(entry.from_time), entry_end, b_s, b_e) for b_s, b_e in breaks
		)
		minutes = max(inside - in_breaks, 0)
		if not minutes:
			continue
		downtime_count += 1
		if entry.is_planned:
			planned_downtime += minutes
		else:
			unplanned_downtime += minutes

	planned_time = max(shift_minutes - break_minutes - planned_downtime, 0)
	run_time = max(planned_time - unplanned_downtime, 0)

	qty = get_quantities(workstation, start, end)
	ideal_cycle_time = flt(frappe.get_cached_value("Workstation", workstation, "ideal_cycle_time_sec"))

	remarks = []
	availability = run_time / planned_time * 100 if planned_time else 0
	performance = quality = 0.0

	if not qty.total_qty:
		remarks.append(_(FLAG_NO_PRODUCTION))
	else:
		quality = qty.good_qty / qty.total_qty * 100
		if not ideal_cycle_time:
			remarks.append(_(FLAG_NO_CYCLE_TIME))
		elif run_time:
			performance = ideal_cycle_time * qty.total_qty / 60 / run_time * 100
			if performance > 100:
				remarks.append(_(FLAG_OVER_100).format(flt(performance, 1)))
				performance = 100.0

	oee = availability * performance * quality / 10000

	return frappe._dict(
		workstation=workstation,
		posting_date=window.shift_date,
		shift=window.shift,
		shift_start=start,
		shift_end=end,
		shift_minutes=flt(shift_minutes, 2),
		break_minutes=flt(break_minutes, 2),
		planned_downtime=flt(planned_downtime, 2),
		unplanned_downtime=flt(unplanned_downtime, 2),
		planned_time=flt(planned_time, 2),
		run_time=flt(run_time, 2),
		downtime_count=downtime_count,
		ideal_cycle_time=ideal_cycle_time,
		total_qty=flt(qty.total_qty, 3),
		good_qty=flt(qty.good_qty, 3),
		rejected_qty=flt(qty.rejected_qty, 3),
		availability=flt(availability, 2),
		performance=flt(performance, 2),
		quality=flt(quality, 2),
		oee=flt(oee, 2),
		is_flagged=1 if remarks else 0,
		remarks="\n".join(remarks),
	)


def get_downtime_entries(workstation: str, start: datetime, end: datetime):
	entry = frappe.qb.DocType("Downtime Entry")
	return (
		frappe.qb.from_(entry)
		.select(entry.name, entry.from_time, entry.to_time, entry.is_planned, entry.downtime_reason)
		.where(
			(entry.workstation == workstation)
			& (entry.from_time < end)
			& (entry.to_time.isnull() | (entry.to_time > start))
		)
		.run(as_dict=True)
	)


def get_quantities(workstation: str, start: datetime, end: datetime) -> frappe._dict:
	source = frappe.db.get_single_value("OEE Settings", "qty_source") or "Job Card"
	if source == "Work Order":
		return get_work_order_quantities(workstation, start, end)
	return get_job_card_quantities(workstation, start, end)


def get_job_card_quantities(workstation: str, start: datetime, end: datetime) -> frappe._dict:
	"""Completed qty from Job Card time logs that ended in the window (start, end].

	Process loss is spread over a Job Card's time logs in proportion to their completed qty. Only
	submitted Job Cards count: on a draft, ERPNext's process_loss_qty still includes the quantity
	that simply has not been made yet.
	"""
	jc = frappe.qb.DocType("Job Card")
	log = frappe.qb.DocType("Job Card Time Log")
	rows = (
		frappe.qb.from_(log)
		.join(jc)
		.on(log.parent == jc.name)
		.select(
			jc.name,
			jc.docstatus,
			log.completed_qty,
			IfNull(jc.total_completed_qty, 0).as_("total_completed_qty"),
			IfNull(jc.process_loss_qty, 0).as_("process_loss_qty"),
		)
		.where(
			(jc.workstation == workstation)
			& (jc.docstatus < 2)
			& (log.parenttype == "Job Card")
			# A log ending exactly at the shift end belongs to that shift, not the next one
			& (log.to_time > start)
			& (log.to_time <= end)
		)
		.run(as_dict=True)
	)

	good = rejected = 0.0
	for row in rows:
		good += flt(row.completed_qty)
		if row.docstatus == 1 and row.process_loss_qty and row.total_completed_qty:
			rejected += flt(row.process_loss_qty) * flt(row.completed_qty) / flt(row.total_completed_qty)

	return frappe._dict(good_qty=good, rejected_qty=rejected, total_qty=good + rejected)


def get_work_order_quantities(workstation: str, start: datetime, end: datetime) -> frappe._dict:
	"""Fallback for sites without Job Cards: Manufacture Stock Entries of Work Orders that have
	an operation on this workstation."""
	se = frappe.qb.DocType("Stock Entry")
	op = frappe.qb.DocType("Work Order Operation")
	work_orders = frappe.qb.from_(op).select(op.parent).where(op.workstation == workstation).distinct()

	rows = (
		frappe.qb.from_(se)
		.select(
			se.posting_date, se.posting_time, se.fg_completed_qty, IfNull(se.process_loss_qty, 0).as_("loss")
		)
		.where(
			(se.docstatus == 1)
			& (se.purpose == "Manufacture")
			& (se.work_order.isin(work_orders))
			& (se.posting_date >= getdate(start))
			& (se.posting_date <= getdate(end))
		)
		.run(as_dict=True)
	)

	total = rejected = 0.0
	for row in rows:
		posted = get_datetime(f"{row.posting_date} {row.posting_time}")
		if start < posted <= end:
			total += flt(row.fg_completed_qty)
			rejected += flt(row.loss)

	return frappe._dict(total_qty=total, rejected_qty=rejected, good_qty=total - rejected)


def get_workstations(workstations: list[str] | None = None) -> list[str]:
	filters = {"disabled": 0}
	if workstations:
		filters["name"] = ("in", workstations)
	return frappe.get_all("Workstation", filters=filters, pluck="name", order_by="name asc")


def build_for_date(posting_date, workstations: list[str] | None = None) -> int:
	"""Create or refresh OEE Logs for every finished shift of `posting_date`. Returns logs written."""
	posting_date = getdate(posting_date)
	now = now_datetime()
	written = 0
	for workstation in get_workstations(workstations):
		for window in get_shift_windows_for_date(workstation, posting_date):
			if window.end > now:
				continue  # shift not over yet
			result = compute_oee(workstation, window)
			existing = frappe.db.get_value(
				"OEE Log",
				{"workstation": workstation, "posting_date": posting_date, "shift": window.shift},
			)
			if not result.planned_time:
				# Whole shift was a planned stop (no production planned): nothing to measure
				if existing:
					frappe.delete_doc("OEE Log", existing, ignore_permissions=True, force=True)
				continue

			log = frappe.get_doc("OEE Log", existing) if existing else frappe.new_doc("OEE Log")
			log.update(result)
			log.flags.ignore_permissions = True
			log.save()
			written += 1
		frappe.db.commit()  # nosemgrep: one workstation at a time keeps long rebuilds resumable
	return written


def build_for_range(from_date, to_date, workstations: list[str] | None = None):
	day = getdate(from_date)
	to_date = getdate(to_date)
	while day <= to_date:
		build_for_date(day, workstations)
		day = getdate(add_days(day, 1))


def build_for_dates(dates: list, workstations: list[str] | None = None):
	"""Refresh OEE Logs for specific days (used when Downtime Entries change after the fact)."""
	for day in sorted({getdate(d) for d in dates}):
		build_for_date(day, workstations)


def build_previous_day():
	"""Daily scheduler job: yesterday's OEE Logs, then the summary email."""
	yesterday = add_days(today(), -1)
	build_for_date(yesterday)

	from oee_tracker.alerts import send_daily_summary

	send_daily_summary(yesterday)


def get_live_oee(posting_date=None, workstations: list[str] | None = None) -> list[frappe._dict]:
	"""OEE so far for shifts of `posting_date` (default today) that have started."""
	posting_date = getdate(posting_date or today())
	now = now_datetime()
	results = []
	for workstation in get_workstations(workstations):
		for window in get_shift_windows_for_date(workstation, posting_date):
			if window.start >= now:
				continue
			result = compute_oee(workstation, window, until=now)
			if result.planned_time:
				results.append(result)
	return results
