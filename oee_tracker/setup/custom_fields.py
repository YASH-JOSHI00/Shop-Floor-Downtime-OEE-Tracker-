"""Custom fields and property setters this app adds to standard ERPNext DocTypes.

Created by `oee_tracker.install` (after_install and after_migrate) with create_custom_fields(),
removed again in before_uninstall. ERPNext core files are never edited.
"""

DOWNTIME_CATEGORIES = "Breakdown\nMaterial\nSetup\nPower\nManpower\nQuality\nOther"


def get_custom_fields():
	return {
		"Downtime Entry": [
			{
				"fieldname": "status",
				"label": "Status",
				"fieldtype": "Select",
				"options": "Open\nClosed",
				"insert_after": "operator",
				"read_only": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"no_copy": 1,
				"description": "Open while the machine is stopped; Closed once To Time is set",
			},
			{
				"fieldname": "shift",
				"label": "Shift",
				"fieldtype": "Link",
				"options": "Shift Definition",
				"insert_after": "status",
				"in_standard_filter": 1,
			},
			{
				"fieldname": "alert_sent",
				"label": "Alert Sent",
				"fieldtype": "Check",
				"insert_after": "shift",
				"hidden": 1,
				"no_copy": 1,
				"read_only": 1,
			},
			{
				"fieldname": "downtime_reason",
				"label": "Downtime Reason",
				"fieldtype": "Link",
				"options": "Downtime Reason",
				"insert_after": "downtime_reason_section",
				"reqd": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "category",
				"label": "Category",
				"fieldtype": "Select",
				"options": DOWNTIME_CATEGORIES,
				"insert_after": "downtime_reason",
				"fetch_from": "downtime_reason.category",
				"read_only": 1,
				"in_standard_filter": 1,
			},
			{
				"fieldname": "is_planned",
				"label": "Is Planned",
				"fieldtype": "Check",
				"insert_after": "category",
				"fetch_from": "downtime_reason.is_planned",
				"read_only": 1,
			},
			{
				"fieldname": "production_reference_section",
				"label": "Production Reference",
				"fieldtype": "Section Break",
				"insert_after": "remarks",
				"collapsible": 1,
			},
			{
				"fieldname": "job_card",
				"label": "Job Card",
				"fieldtype": "Link",
				"options": "Job Card",
				"insert_after": "production_reference_section",
			},
			{
				"fieldname": "production_reference_column",
				"fieldtype": "Column Break",
				"insert_after": "job_card",
			},
			{
				"fieldname": "work_order",
				"label": "Work Order",
				"fieldtype": "Link",
				"options": "Work Order",
				"insert_after": "production_reference_column",
				"fetch_from": "job_card.work_order",
				"fetch_if_empty": 1,
			},
		],
		"Workstation": [
			{
				"fieldname": "oee_section",
				"label": "OEE",
				"fieldtype": "Section Break",
				"insert_after": "plant_floor",
			},
			{
				"fieldname": "ideal_cycle_time_sec",
				"label": "Ideal Cycle Time (Seconds per Unit)",
				"fieldtype": "Float",
				"insert_after": "oee_section",
				"description": "Seconds per unit at rated speed; used for OEE Performance",
			},
			{
				"fieldname": "default_shift",
				"label": "Default Shift",
				"fieldtype": "Link",
				"options": "Shift Definition",
				"insert_after": "ideal_cycle_time_sec",
				"description": "Leave empty if this machine runs every enabled shift",
			},
			{
				"fieldname": "oee_column_break",
				"fieldtype": "Column Break",
				"insert_after": "default_shift",
			},
			{
				"fieldname": "current_status",
				"label": "Current Status",
				"fieldtype": "Select",
				"options": "Running\nStopped\nIdle",
				"default": "Running",
				"insert_after": "oee_column_break",
				"read_only": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
				"no_copy": 1,
			},
		],
		"Job Card": [
			{
				"fieldname": "downtime_minutes",
				"label": "Downtime (Minutes)",
				"fieldtype": "Float",
				"insert_after": "total_time_in_mins",
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
				"description": "Total of closed Downtime Entries linked to this Job Card",
			},
		],
	}


# (doctype, fieldname, property, value, property_type)
PROPERTY_SETTERS = [
	# Keep the standard Select for old entries and the standard Downtime Analysis report,
	# but fill it from Downtime Reason.legacy_stop_reason instead of asking the user.
	("Downtime Entry", "stop_reason", "hidden", "1", "Check"),
	("Downtime Entry", "stop_reason", "reqd", "0", "Check"),
	# An Open entry has no To Time yet.
	("Downtime Entry", "to_time", "reqd", "0", "Check"),
	# The operator screen logs stops for users who may not be linked to an Employee.
	("Downtime Entry", "operator", "reqd", "0", "Check"),
]
