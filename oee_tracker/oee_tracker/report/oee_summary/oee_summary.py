# Copyright (c) 2026, yashjoshi and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from oee_tracker.report_utils import aggregate_oee, get_oee_logs, oee_columns, validate_dates

GROUPINGS = {
	"Workstation and Date": ("workstation", "posting_date"),
	"Workstation": ("workstation",),
	"Date": ("posting_date",),
	"Shift Log": ("workstation", "posting_date", "shift"),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_dates(filters)
	keys = GROUPINGS.get(filters.get("group_by") or "Workstation and Date", GROUPINGS["Workstation and Date"])

	logs = get_oee_logs(filters)
	groups = {}
	for log in logs:
		groups.setdefault(tuple(log.get(k) for k in keys), []).append(log)

	data = []
	for key, rows in groups.items():
		row = aggregate_oee(rows)
		row.update(dict(zip(keys, key, strict=True)))
		if "shift" in keys:
			row.remarks = rows[0].remarks
		data.append(row)

	target = flt(frappe.db.get_single_value("OEE Settings", "oee_target")) or 85
	overall = aggregate_oee(logs) if logs else None
	return (
		get_columns(keys),
		data,
		None,
		get_chart(logs, target),
		get_summary(overall, target),
	)


def get_columns(keys):
	columns = []
	if "posting_date" in keys:
		columns.append({"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100})
	if "workstation" in keys:
		columns.append(
			{
				"label": _("Workstation"),
				"fieldname": "workstation",
				"fieldtype": "Link",
				"options": "Workstation",
				"width": 150,
			}
		)
	if "shift" in keys:
		columns.append(
			{
				"label": _("Shift"),
				"fieldname": "shift",
				"fieldtype": "Link",
				"options": "Shift Definition",
				"width": 120,
			}
		)
	else:
		columns.append({"label": _("Shifts"), "fieldname": "shifts", "fieldtype": "Int", "width": 70})
	columns += oee_columns()
	if "shift" in keys:
		columns.append({"label": _("Flags"), "fieldname": "remarks", "fieldtype": "Data", "width": 250})
	else:
		columns.append(
			{"label": _("Flagged Shifts"), "fieldname": "flagged", "fieldtype": "Int", "width": 110}
		)
	return columns


def get_chart(logs, target):
	if not logs:
		return None
	by_date = {}
	for log in logs:
		by_date.setdefault(log.posting_date, []).append(log)
	dates = sorted(by_date)
	points = [aggregate_oee(by_date[d]) for d in dates]
	return {
		"data": {
			"labels": [frappe.format(d, {"fieldtype": "Date"}) for d in dates],
			"datasets": [
				{"name": _("OEE"), "values": [p.oee for p in points]},
				{"name": _("Availability"), "values": [p.availability for p in points]},
				{"name": _("Performance"), "values": [p.performance for p in points]},
				{"name": _("Quality"), "values": [p.quality for p in points]},
			],
			"yMarkers": [{"label": _("Target"), "value": target}],
		},
		"type": "line",
		"colors": ["#29CD42", "#449CF0", "#ECAD4B", "#7575FF"],
		"lineOptions": {"regionFill": 0, "dotSize": 3},
		"axisOptions": {"xIsSeries": 1},
	}


def get_summary(overall, target):
	if not overall:
		return None
	return [
		{
			"label": _("OEE"),
			"value": overall.oee,
			"datatype": "Percent",
			"indicator": "Green" if overall.oee >= target else "Red",
		},
		{
			"label": _("Availability"),
			"value": overall.availability,
			"datatype": "Percent",
			"indicator": "Blue",
		},
		{"label": _("Performance"), "value": overall.performance, "datatype": "Percent", "indicator": "Blue"},
		{"label": _("Quality"), "value": overall.quality, "datatype": "Percent", "indicator": "Blue"},
		{"label": _("Target"), "value": target, "datatype": "Percent", "indicator": "Grey"},
	]
