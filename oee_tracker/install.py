"""Install / migrate / uninstall hooks.

Everything here is idempotent: after_migrate re-runs it so client sites pick up new custom
fields, permissions and dashboard widgets on every `bench migrate`.
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import setup_custom_perms

from oee_tracker.setup.custom_fields import PROPERTY_SETTERS, get_custom_fields

APP_ROLES = ("Shopfloor Operator", "Shopfloor Supervisor", "Maintenance User")

# Permissions this app adds on standard DocTypes, as Custom DocPerm rows.
# setup_custom_perms() copies the standard rows first, so existing roles keep their access.
STANDARD_DOCTYPE_PERMISSIONS = {
	"Downtime Entry": {
		"Shopfloor Operator": {"read": 1, "write": 1, "create": 1, "select": 1, "if_owner": 1},
		"Shopfloor Supervisor": {
			"read": 1,
			"write": 1,
			"create": 1,
			"delete": 1,
			"select": 1,
			"report": 1,
			"export": 1,
			"print": 1,
			"email": 1,
			"share": 1,
		},
		"Maintenance User": {"read": 1, "write": 1, "select": 1, "report": 1, "print": 1},
	},
	"Workstation": {
		"Shopfloor Operator": {"read": 1, "select": 1},
		"Shopfloor Supervisor": {"read": 1, "select": 1, "report": 1},
		"Maintenance User": {"read": 1, "select": 1},
	},
	"Plant Floor": {
		"Shopfloor Operator": {"read": 1, "select": 1},
		"Shopfloor Supervisor": {"read": 1, "select": 1},
	},
	"Job Card": {
		"Shopfloor Operator": {"select": 1},
		"Shopfloor Supervisor": {"read": 1, "select": 1, "report": 1},
	},
	"Work Order": {
		"Shopfloor Operator": {"select": 1},
		"Shopfloor Supervisor": {"read": 1, "select": 1, "report": 1},
	},
}

PERM_FIELDS = (
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"import",
	"share",
	"print",
	"email",
	"select",
)

DEFAULT_REASONS = [
	# reason_name, category, is_planned, notify_role, legacy_stop_reason
	("Machine Breakdown", "Breakdown", 0, "Maintenance User", "Machine malfunction"),
	("Unplanned Maintenance", "Breakdown", 0, "Maintenance User", "Unplanned machine maintenance"),
	("Setup / Changeover", "Setup", 0, None, "Excessive machine set up time"),
	("Waiting for Material", "Material", 0, None, "Other"),
	("Power Cut", "Power", 0, "Maintenance User", "Electricity down"),
	("Operator Not Available", "Manpower", 0, None, "Other"),
	("Operator Error", "Manpower", 0, None, "Machine operator errors"),
	("On-machine Quality Check", "Quality", 0, None, "On-machine press checks"),
	("Quality Issue", "Quality", 0, None, "Other"),
	("Planned Maintenance", "Other", 1, None, "Other"),
	("No Production Planned", "Other", 1, None, "Other"),
	("Other", "Other", 0, None, "Other"),
]

NUMBER_CARDS = [
	{
		"name": "Today's OEE",
		"type": "Custom",
		"document_type": "OEE Log",
		"method": "oee_tracker.api.get_todays_oee_card",
		"color": "#29CD42",
	},
	{
		"name": "Downtime Minutes Today",
		"type": "Custom",
		"document_type": "Downtime Entry",
		"method": "oee_tracker.api.get_downtime_today_card",
		"color": "#ECAD4B",
	},
	{
		"name": "Machines Stopped Now",
		"type": "Document Type",
		"document_type": "Workstation",
		"function": "Count",
		"filters_json": json.dumps([["Workstation", "current_status", "=", "Stopped", False]]),
		"color": "#E24C4C",
	},
	{
		"name": "Open Breakdowns",
		"type": "Document Type",
		"document_type": "Downtime Entry",
		"function": "Count",
		"filters_json": json.dumps(
			[
				["Downtime Entry", "status", "=", "Open", False],
				["Downtime Entry", "category", "=", "Breakdown", False],
			]
		),
		"color": "#E24C4C",
	},
]

LAST_30_DAYS = "frappe.datetime.add_days(frappe.datetime.get_today(), -30)"

DASHBOARD_CHARTS = [
	{
		"name": "OEE Trend",
		"chart_type": "Average",
		"document_type": "OEE Log",
		"based_on": "posting_date",
		"value_based_on": "oee",
		"timeseries": 1,
		"timespan": "Last Month",
		"time_interval": "Daily",
		"type": "Line",
		"filters_json": "[]",
		"color": "#449CF0",
	},
	{
		"name": "Top 5 Downtime Reasons",
		"chart_type": "Group By",
		"document_type": "Downtime Entry",
		"group_by_based_on": "downtime_reason",
		"group_by_type": "Sum",
		"aggregate_function_based_on": "downtime",
		"number_of_groups": 5,
		"type": "Bar",
		# Losses only: planned stops (No Production Planned, Planned Maintenance) are not losses
		"filters_json": json.dumps([["Downtime Entry", "is_planned", "=", 0, False]]),
		# Rolling last 30 days, evaluated in the browser when the chart loads. (The "last month"
		# timespan means the previous calendar month, which hides everything from this month.)
		"dynamic_filters_json": json.dumps([["Downtime Entry", "from_time", ">=", LAST_30_DAYS]]),
		"color": "#E24C4C",
	},
	{
		"name": "OEE by Workstation",
		"chart_type": "Group By",
		"document_type": "OEE Log",
		"group_by_based_on": "workstation",
		"group_by_type": "Average",
		"aggregate_function_based_on": "oee",
		"number_of_groups": 0,
		"type": "Bar",
		"filters_json": "[]",
		"dynamic_filters_json": json.dumps([["OEE Log", "posting_date", ">=", LAST_30_DAYS]]),
		"color": "#29CD42",
	},
]


def after_install():
	setup()
	create_default_reasons()
	create_default_shift()
	set_default_settings()

	from oee_tracker.patches.backfill_downtime_reason import backfill

	# Patches are marked as done on a fresh install, so run the back-fill here as well
	backfill()


def after_migrate():
	setup()


def setup():
	ensure_roles()
	create_custom_fields(get_custom_fields(), ignore_validate=True)
	create_property_setters()
	setup_permissions()
	create_dashboard_widgets()


def before_uninstall():
	delete_custom_fields(get_custom_fields())
	for doctype, fieldname, prop, _value, _ptype in PROPERTY_SETTERS:
		frappe.db.delete("Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": prop})
	for doctype in STANDARD_DOCTYPE_PERMISSIONS:
		frappe.db.delete(
			"Custom DocPerm",
			{"parent": doctype, "role": ("in", ["Shopfloor Operator", "Shopfloor Supervisor"])},
		)
		frappe.clear_cache(doctype=doctype)
	for card in NUMBER_CARDS:
		frappe.delete_doc("Number Card", card["name"], ignore_missing=True, force=True)
	for chart in DASHBOARD_CHARTS:
		frappe.delete_doc("Dashboard Chart", chart["name"], ignore_missing=True, force=True)


def ensure_roles():
	for role in APP_ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)


def create_property_setters():
	for doctype, fieldname, prop, value, ptype in PROPERTY_SETTERS:
		make_property_setter(doctype, fieldname, prop, value, ptype, validate_fields_for_doctype=False)


def setup_permissions():
	for doctype, roles in STANDARD_DOCTYPE_PERMISSIONS.items():
		setup_custom_perms(doctype)
		for role, perms in roles.items():
			if_owner = perms.get("if_owner", 0)
			values = {field: perms.get(field, 0) for field in PERM_FIELDS}
			existing = frappe.db.get_value(
				"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": if_owner}
			)
			if existing:
				# Never take away access a site admin granted on top of ours
				current = frappe.db.get_value("Custom DocPerm", existing, list(PERM_FIELDS), as_dict=True)
				merged = {field: max(values[field], current[field] or 0) for field in PERM_FIELDS}
				frappe.db.set_value("Custom DocPerm", existing, merged)
			else:
				frappe.get_doc(
					{
						"doctype": "Custom DocPerm",
						"parent": doctype,
						"parenttype": "DocType",
						"parentfield": "permissions",
						"role": role,
						"permlevel": 0,
						"if_owner": if_owner,
						**values,
					}
				).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)


def create_dashboard_widgets():
	for card in NUMBER_CARDS:
		values = {
			"doctype": "Number Card",
			"label": card["name"],
			"is_public": 1,
			"is_standard": 0,
			"module": "OEE Tracker",
			"show_percentage_stats": 0,
			**{k: v for k, v in card.items() if k != "name"},
		}
		_upsert("Number Card", card["name"], values)
		# Frappe fills Currency with the system default (e.g. INR) on insert, and a card with a
		# currency is formatted as money. These cards show percentages, minutes and counts.
		frappe.db.set_value("Number Card", card["name"], "currency", None, update_modified=False)

	for chart in DASHBOARD_CHARTS:
		values = {
			"doctype": "Dashboard Chart",
			"chart_name": chart["name"],
			"is_public": 1,
			"is_standard": 0,
			"module": "OEE Tracker",
			**{k: v for k, v in chart.items() if k != "name"},
		}
		_upsert("Dashboard Chart", chart["name"], values)


def _upsert(doctype, name, values):
	if frappe.db.exists(doctype, name):
		doc = frappe.get_doc(doctype, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(values)
		doc.name = name
		doc.flags.name_set = True
		doc.insert(ignore_permissions=True, set_name=name)


def create_default_reasons():
	for reason_name, category, is_planned, notify_role, legacy in DEFAULT_REASONS:
		if frappe.db.exists("Downtime Reason", reason_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Downtime Reason",
				"reason_name": reason_name,
				"category": category,
				"is_planned": is_planned,
				"notify_role": notify_role if notify_role and frappe.db.exists("Role", notify_role) else None,
				"legacy_stop_reason": legacy,
			}
		).insert(ignore_permissions=True)


def create_default_shift():
	if frappe.db.count("Shift Definition"):
		return
	frappe.get_doc(
		{
			"doctype": "Shift Definition",
			"shift_name": "General Shift",
			"start_time": "09:00:00",
			"end_time": "18:00:00",
			"breaks": [
				{"break_name": "Lunch", "from_time": "13:00:00", "to_time": "13:45:00"},
				{"break_name": "Tea", "from_time": "16:00:00", "to_time": "16:15:00"},
			],
		}
	).insert(ignore_permissions=True)


def set_default_settings():
	settings = frappe.get_single("OEE Settings")
	if not settings.default_shift:
		settings.default_shift = frappe.db.get_value("Shift Definition", {"disabled": 0}, "name")
	if not settings.alert_roles:
		for role in ("Maintenance User", "Shopfloor Supervisor"):
			settings.append("alert_roles", {"role": role})
	if not settings.summary_roles:
		settings.append("summary_roles", {"role": "Manufacturing Manager"})
	settings.flags.ignore_permissions = True
	settings.save()
