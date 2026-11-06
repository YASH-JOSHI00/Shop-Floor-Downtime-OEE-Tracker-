# Copyright (c) 2026, yashjoshi and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from oee_tracker.report_utils import get_downtime_entries, validate_dates


def execute(filters=None):
	"""Per machine: breakdown count, MTTR = repair minutes / breakdowns,
	MTBF = operating (run) minutes / breakdowns. Run time comes from OEE Logs."""
	filters = frappe._dict(filters or {})
	validate_dates(filters)
	if not filters.get("category"):
		filters.category = "Breakdown"

	entries = get_downtime_entries(filters)
	run_time = get_run_time(filters)

	machines = {}
	for row in entries:
		m = machines.setdefault(
			row.workstation, frappe._dict(workstation=row.workstation, failures=0, repair=0.0, longest=0.0)
		)
		m.failures += 1
		m.repair += flt(row.downtime)
		m.longest = max(m.longest, flt(row.downtime))

	data = []
	for ws, _operating in run_time.items():
		machines.setdefault(ws, frappe._dict(workstation=ws, failures=0, repair=0.0, longest=0.0))
	for m in machines.values():
		m.operating_time = flt(run_time.get(m.workstation), 2)
		m.repair = flt(m.repair, 2)
		m.longest = flt(m.longest, 2)
		m.mttr = flt(m.repair / m.failures, 2) if m.failures else None
		m.mtbf = flt(m.operating_time / m.failures, 2) if m.failures and m.operating_time else None
		m.mtbf_hours = flt(m.mtbf / 60, 2) if m.mtbf else None
		data.append(m)

	data.sort(key=lambda m: (-m.failures, -m.repair))
	return get_columns(), data, None, get_chart(data)


def get_run_time(filters):
	log = frappe.qb.DocType("OEE Log")
	ws = frappe.qb.DocType("Workstation")
	query = (
		frappe.qb.from_(log)
		.left_join(ws)
		.on(log.workstation == ws.name)
		.select(log.workstation, frappe.query_builder.functions.Sum(log.run_time))
		.where((log.posting_date >= filters.from_date) & (log.posting_date <= filters.to_date))
		.groupby(log.workstation)
	)
	if filters.get("workstation"):
		query = query.where(log.workstation == filters.workstation)
	if filters.get("plant_floor"):
		query = query.where(ws.plant_floor == filters.plant_floor)
	return dict(query.run())


def get_columns():
	return [
		{
			"label": _("Workstation"),
			"fieldname": "workstation",
			"fieldtype": "Link",
			"options": "Workstation",
			"width": 170,
		},
		{"label": _("Failures"), "fieldname": "failures", "fieldtype": "Int", "width": 90},
		{"label": _("Repair Time (min)"), "fieldname": "repair", "fieldtype": "Float", "width": 140},
		{"label": _("Longest Stop (min)"), "fieldname": "longest", "fieldtype": "Float", "width": 140},
		{
			"label": _("Operating Time (min)"),
			"fieldname": "operating_time",
			"fieldtype": "Float",
			"width": 160,
		},
		{"label": _("MTTR (min)"), "fieldname": "mttr", "fieldtype": "Float", "width": 110},
		{"label": _("MTBF (min)"), "fieldname": "mtbf", "fieldtype": "Float", "width": 110},
		{"label": _("MTBF (hrs)"), "fieldname": "mtbf_hours", "fieldtype": "Float", "width": 110},
	]


def get_chart(data):
	data = [m for m in data if m.failures][:15]
	if not data:
		return None
	return {
		"data": {
			"labels": [m.workstation for m in data],
			"datasets": [{"name": _("MTTR (min)"), "values": [m.mttr or 0 for m in data]}],
		},
		"type": "bar",
		"colors": ["#E24C4C"],
	}
