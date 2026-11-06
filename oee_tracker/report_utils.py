"""Helpers shared by the OEE Tracker script reports."""

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, now_datetime


def validate_dates(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required"))
	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))


def date_range_datetimes(filters):
	"""[from_date 00:00, to_date + 1 day 00:00)"""
	return get_datetime(filters.from_date), get_datetime(add_days(filters.to_date, 1))


def get_downtime_entries(filters, extra_fields=(), exclude_planned=False):
	"""Downtime Entries that started in the date range, with minutes for open entries counted to now."""
	start, end = date_range_datetimes(filters)
	entry = frappe.qb.DocType("Downtime Entry")
	ws = frappe.qb.DocType("Workstation")
	query = (
		frappe.qb.from_(entry)
		.left_join(ws)
		.on(entry.workstation == ws.name)
		.select(
			entry.name,
			entry.workstation,
			entry.from_time,
			entry.to_time,
			entry.downtime,
			entry.downtime_reason,
			entry.category,
			entry.is_planned,
			entry.status,
			entry.shift,
			entry.operator,
			*[entry[f] for f in extra_fields],
		)
		.where((entry.from_time >= start) & (entry.from_time < end))
		.orderby(entry.from_time)
	)
	for field in ("workstation", "downtime_reason", "category", "shift", "status", "operator"):
		if filters.get(field):
			query = query.where(entry[field] == filters.get(field))
	if filters.get("plant_floor"):
		query = query.where(ws.plant_floor == filters.plant_floor)
	if exclude_planned:
		query = query.where(entry.is_planned == 0)

	rows = query.run(as_dict=True)
	now = now_datetime()
	for row in rows:
		if row.status == "Open" or not row.to_time:
			row.downtime = (now - get_datetime(row.from_time)).total_seconds() / 60
		row.downtime = flt(row.downtime, 2)
	return rows


def get_oee_logs(filters):
	log = frappe.qb.DocType("OEE Log")
	ws = frappe.qb.DocType("Workstation")
	query = (
		frappe.qb.from_(log)
		.left_join(ws)
		.on(log.workstation == ws.name)
		.select(
			log.name,
			log.workstation,
			log.posting_date,
			log.shift,
			log.shift_start,
			log.planned_time,
			log.run_time,
			log.planned_downtime,
			log.unplanned_downtime,
			log.downtime_count,
			log.ideal_cycle_time,
			log.total_qty,
			log.good_qty,
			log.rejected_qty,
			log.availability,
			log.performance,
			log.quality,
			log.oee,
			log.is_flagged,
			log.remarks,
		)
		.where((log.posting_date >= filters.from_date) & (log.posting_date <= filters.to_date))
		.orderby(log.posting_date)
		.orderby(log.workstation)
		.orderby(log.shift_start)
	)
	for field in ("workstation", "shift"):
		if filters.get(field):
			query = query.where(log[field] == filters.get(field))
	if filters.get("plant_floor"):
		query = query.where(ws.plant_floor == filters.plant_floor)
	return query.run(as_dict=True)


def aggregate_oee(logs) -> frappe._dict:
	"""Time- and quantity-weighted OEE over several OEE Logs (not an average of percentages)."""
	planned = sum(flt(r.planned_time) for r in logs)
	run = sum(flt(r.run_time) for r in logs)
	total = sum(flt(r.total_qty) for r in logs)
	good = sum(flt(r.good_qty) for r in logs)
	# Same cap as the per-shift calculation: a shift can contribute at most its own run time
	ideal_minutes = sum(min(flt(r.performance) / 100 * flt(r.run_time), flt(r.run_time)) for r in logs)

	availability = run / planned * 100 if planned else 0
	performance = ideal_minutes / run * 100 if run else 0
	quality = good / total * 100 if total else 0
	return frappe._dict(
		shifts=len(logs),
		planned_time=flt(planned, 2),
		run_time=flt(run, 2),
		planned_downtime=flt(sum(flt(r.planned_downtime) for r in logs), 2),
		unplanned_downtime=flt(sum(flt(r.unplanned_downtime) for r in logs), 2),
		downtime_count=sum(r.downtime_count or 0 for r in logs),
		total_qty=flt(total, 3),
		good_qty=flt(good, 3),
		rejected_qty=flt(sum(flt(r.rejected_qty) for r in logs), 3),
		availability=flt(availability, 2),
		performance=flt(performance, 2),
		quality=flt(quality, 2),
		oee=flt(availability * performance * quality / 10000, 2),
		flagged=sum(1 for r in logs if r.is_flagged),
	)


def oee_columns():
	return [
		{"label": _("Planned Time (min)"), "fieldname": "planned_time", "fieldtype": "Float", "width": 130},
		{"label": _("Run Time (min)"), "fieldname": "run_time", "fieldtype": "Float", "width": 110},
		{
			"label": _("Unplanned Downtime (min)"),
			"fieldname": "unplanned_downtime",
			"fieldtype": "Float",
			"width": 160,
		},
		{"label": _("Stops"), "fieldname": "downtime_count", "fieldtype": "Int", "width": 70},
		{"label": _("Total Qty"), "fieldname": "total_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Good Qty"), "fieldname": "good_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Availability"), "fieldname": "availability", "fieldtype": "Percent", "width": 100},
		{"label": _("Performance"), "fieldname": "performance", "fieldtype": "Percent", "width": 110},
		{"label": _("Quality"), "fieldname": "quality", "fieldtype": "Percent", "width": 90},
		{"label": _("OEE"), "fieldname": "oee", "fieldtype": "Percent", "width": 90},
	]
