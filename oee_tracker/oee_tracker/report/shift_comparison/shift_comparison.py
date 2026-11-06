# Copyright (c) 2026, yashjoshi and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from oee_tracker.report_utils import (
	aggregate_oee,
	get_downtime_entries,
	get_oee_logs,
	oee_columns,
	validate_dates,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_dates(filters)
	if filters.get("group_by") == "Operator":
		return execute_by_operator(filters)
	return execute_by_shift(filters)


def execute_by_shift(filters):
	logs = get_oee_logs(filters)
	groups = {}
	for log in logs:
		groups.setdefault(log.shift or _("Not Set"), []).append(log)

	data = []
	for shift, rows in groups.items():
		row = aggregate_oee(rows)
		row.shift = shift
		data.append(row)
	data.sort(key=lambda r: r.oee, reverse=True)

	columns = [
		{
			"label": _("Shift"),
			"fieldname": "shift",
			"fieldtype": "Link",
			"options": "Shift Definition",
			"width": 140,
		},
		{"label": _("Shift Logs"), "fieldname": "shifts", "fieldtype": "Int", "width": 90},
		*oee_columns(),
	]
	chart = None
	if data:
		chart = {
			"data": {
				"labels": [r.shift for r in data],
				"datasets": [
					{"name": _("Availability"), "values": [r.availability for r in data]},
					{"name": _("Performance"), "values": [r.performance for r in data]},
					{"name": _("Quality"), "values": [r.quality for r in data]},
					{"name": _("OEE"), "values": [r.oee for r in data]},
				],
			},
			"type": "bar",
			"colors": ["#449CF0", "#ECAD4B", "#7575FF", "#29CD42"],
		}
	return columns, data, None, chart


def execute_by_operator(filters):
	entries = get_downtime_entries(filters)
	groups = {}
	for row in entries:
		key = (row.operator or "", row.shift or "")
		g = groups.setdefault(
			key,
			frappe._dict(
				operator=row.operator, shift=row.shift, stops=0, minutes=0.0, unplanned=0.0, breakdowns=0
			),
		)
		g.stops += 1
		g.minutes += flt(row.downtime)
		if not row.is_planned:
			g.unplanned += flt(row.downtime)
		if row.category == "Breakdown":
			g.breakdowns += 1

	data = sorted(groups.values(), key=lambda g: g.unplanned, reverse=True)
	for g in data:
		g.operator_name = g.operator and frappe.get_cached_value("Employee", g.operator, "employee_name")
		g.avg = flt(g.minutes / g.stops, 2) if g.stops else 0
		g.minutes = flt(g.minutes, 2)
		g.unplanned = flt(g.unplanned, 2)

	columns = [
		{
			"label": _("Operator"),
			"fieldname": "operator",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{"label": _("Operator Name"), "fieldname": "operator_name", "fieldtype": "Data", "width": 160},
		{
			"label": _("Shift"),
			"fieldname": "shift",
			"fieldtype": "Link",
			"options": "Shift Definition",
			"width": 130,
		},
		{"label": _("Stops"), "fieldname": "stops", "fieldtype": "Int", "width": 80},
		{"label": _("Breakdowns"), "fieldname": "breakdowns", "fieldtype": "Int", "width": 100},
		{"label": _("Downtime (min)"), "fieldname": "minutes", "fieldtype": "Float", "width": 130},
		{
			"label": _("Unplanned Downtime (min)"),
			"fieldname": "unplanned",
			"fieldtype": "Float",
			"width": 170,
		},
		{"label": _("Avg per Stop (min)"), "fieldname": "avg", "fieldtype": "Float", "width": 140},
	]
	return columns, data
