# Copyright (c) 2026, yashjoshi and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from oee_tracker.report_utils import get_downtime_entries, validate_dates


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_dates(filters)
	data = get_downtime_entries(filters, extra_fields=("job_card", "work_order", "remarks"))
	return get_columns(), data


def get_columns():
	return [
		{
			"label": _("Downtime Entry"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Downtime Entry",
			"width": 130,
		},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 80},
		{
			"label": _("Workstation"),
			"fieldname": "workstation",
			"fieldtype": "Link",
			"options": "Workstation",
			"width": 150,
		},
		{"label": _("From Time"), "fieldname": "from_time", "fieldtype": "Datetime", "width": 160},
		{"label": _("To Time"), "fieldname": "to_time", "fieldtype": "Datetime", "width": 160},
		{"label": _("Downtime (min)"), "fieldname": "downtime", "fieldtype": "Float", "width": 120},
		{
			"label": _("Downtime Reason"),
			"fieldname": "downtime_reason",
			"fieldtype": "Link",
			"options": "Downtime Reason",
			"width": 170,
		},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 100},
		{"label": _("Planned"), "fieldname": "is_planned", "fieldtype": "Check", "width": 70},
		{
			"label": _("Shift"),
			"fieldname": "shift",
			"fieldtype": "Link",
			"options": "Shift Definition",
			"width": 120,
		},
		{
			"label": _("Operator"),
			"fieldname": "operator",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"label": _("Job Card"),
			"fieldname": "job_card",
			"fieldtype": "Link",
			"options": "Job Card",
			"width": 130,
		},
		{
			"label": _("Work Order"),
			"fieldname": "work_order",
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 130,
		},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 220},
	]
