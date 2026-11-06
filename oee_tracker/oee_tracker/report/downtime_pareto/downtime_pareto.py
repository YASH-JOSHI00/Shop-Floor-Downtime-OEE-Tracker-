# Copyright (c) 2026, yashjoshi and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from oee_tracker.report_utils import get_downtime_entries, validate_dates


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_dates(filters)
	group_by = "category" if filters.get("group_by") == "Category" else "downtime_reason"

	entries = get_downtime_entries(filters, exclude_planned=not filters.get("include_planned"))
	groups = {}
	for row in entries:
		key = row.get(group_by) or _("Not Set")
		group = groups.setdefault(key, frappe._dict(name=key, category=row.category, count=0, minutes=0.0))
		group.count += 1
		group.minutes += flt(row.downtime)

	total = sum(g.minutes for g in groups.values())
	data = sorted(groups.values(), key=lambda g: g.minutes, reverse=True)
	cumulative = 0.0
	for row in data:
		cumulative += row.minutes
		row.minutes = flt(row.minutes, 2)
		row.hours = flt(row.minutes / 60, 2)
		row.avg_minutes = flt(row.minutes / row.count, 2) if row.count else 0
		row.share = flt(row.minutes / total * 100, 2) if total else 0
		row.cumulative = flt(cumulative / total * 100, 2) if total else 0

	return get_columns(group_by), data, None, get_chart(data), get_summary(data, total)


def get_columns(group_by):
	columns = []
	if group_by == "category":
		columns.append({"label": _("Category"), "fieldname": "name", "fieldtype": "Data", "width": 160})
	else:
		columns += [
			{
				"label": _("Downtime Reason"),
				"fieldname": "name",
				"fieldtype": "Link",
				"options": "Downtime Reason",
				"width": 200,
			},
			{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 120},
		]
	return [
		*columns,
		{"label": _("Stops"), "fieldname": "count", "fieldtype": "Int", "width": 80},
		{"label": _("Downtime (min)"), "fieldname": "minutes", "fieldtype": "Float", "width": 130},
		{"label": _("Downtime (hrs)"), "fieldname": "hours", "fieldtype": "Float", "width": 120},
		{"label": _("Avg per Stop (min)"), "fieldname": "avg_minutes", "fieldtype": "Float", "width": 140},
		{"label": _("% of Total"), "fieldname": "share", "fieldtype": "Percent", "width": 100},
		{"label": _("Cumulative %"), "fieldname": "cumulative", "fieldtype": "Percent", "width": 120},
	]


def get_chart(data):
	if not data:
		return None
	data = data[:15]
	return {
		"data": {
			"labels": [_(row.name) for row in data],
			"datasets": [
				{"name": _("Downtime (min)"), "values": [row.minutes for row in data], "chartType": "bar"},
				{"name": _("Cumulative %"), "values": [row.cumulative for row in data], "chartType": "line"},
			],
		},
		"type": "axis-mixed",
		"colors": ["#E24C4C", "#449CF0"],
		"barOptions": {"spaceRatio": 0.4},
	}


def get_summary(data, total):
	if not data:
		return None
	return [
		{
			"label": _("Total Downtime (hrs)"),
			"value": flt(total / 60, 2),
			"datatype": "Float",
			"indicator": "Red",
		},
		{"label": _("Stops"), "value": sum(r.count for r in data), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Top Cause"), "value": _(data[0].name), "datatype": "Data", "indicator": "Orange"},
	]
