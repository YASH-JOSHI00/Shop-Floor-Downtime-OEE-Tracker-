"""Whitelisted methods for the operator screen (/desk/shopfloor) and the OEE Tracker workspace."""

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, get_datetime, now_datetime, today

from oee_tracker.shift import overlap_minutes


def _check_workstation_access(workstation: str):
	if not frappe.db.exists("Workstation", workstation):
		frappe.throw(_("Workstation {0} not found").format(workstation), frappe.DoesNotExistError)
	# Respects User Permissions, so operators only reach their assigned machines
	frappe.has_permission("Workstation", "read", doc=workstation, throw=True)


@frappe.whitelist()
def get_plant_floors() -> list[str]:
	return frappe.get_list("Plant Floor", pluck="name", order_by="name asc")


@frappe.whitelist()
def get_workstation_status(plant_floor: str | None = None) -> list[dict]:
	frappe.has_permission("Workstation", "read", throw=True)
	filters = {"disabled": 0}
	if plant_floor:
		filters["plant_floor"] = plant_floor

	workstations = frappe.get_list(
		"Workstation",
		filters=filters,
		fields=["name", "workstation_name", "plant_floor", "current_status", "workstation_type"],
		order_by="plant_floor asc, name asc",
		limit_page_length=0,
	)
	if not workstations:
		return []

	open_entries = {
		row.workstation: row
		for row in frappe.get_all(
			"Downtime Entry",
			filters={"status": "Open", "workstation": ("in", [ws.name for ws in workstations])},
			fields=["name", "workstation", "from_time", "downtime_reason", "category", "owner"],
		)
	}

	now = now_datetime()
	for ws in workstations:
		entry = open_entries.get(ws.name)
		ws.status = "Stopped" if entry else ("Idle" if ws.current_status == "Idle" else "Running")
		if entry:
			ws.downtime_entry = entry.name
			ws.from_time = entry.from_time
			ws.downtime_reason = entry.downtime_reason
			ws.category = entry.category
			ws.minutes_stopped = int((now - get_datetime(entry.from_time)).total_seconds() // 60)
	return workstations


JOB_CARD_STATE_ORDER = {"Stopped": 0, "Running": 1, "Paused": 2, "Not Started": 3, "To Submit": 4}


@frappe.whitelist()
def get_job_card_status(plant_floor: str | None = None) -> list[dict]:
	"""One row per draft Job Card on the workstations this user can see.

	State comes from the Job Card itself, not from the Workstation:
	  Stopped      an open Downtime Entry on its workstation while it runs (or one linked to it)
	  Running      a time log has been started and not ended (and the card is not paused)
	  Paused       work has started but no time log is open
	  To Submit    all time logs closed and the full quantity is done; waiting to be submitted
	  Not Started  no time logs yet
	Submitted and cancelled Job Cards drop off the screen.
	"""
	frappe.has_permission("Workstation", "read", throw=True)
	ws_filters = {"disabled": 0}
	if plant_floor:
		ws_filters["plant_floor"] = plant_floor

	# get_list respects User Permissions, so operators only see their assigned machines
	workstations = {
		ws.name: ws
		for ws in frappe.get_list(
			"Workstation",
			filters=ws_filters,
			fields=["name", "workstation_name", "plant_floor"],
			limit_page_length=0,
		)
	}
	if not workstations:
		return []

	# Operators only have "select" on Job Card, so read them here once workstation access is checked
	job_cards = frappe.get_all(
		"Job Card",
		filters={"docstatus": 0, "workstation": ("in", list(workstations))},
		fields=[
			"name",
			"operation",
			"work_order",
			"production_item",
			"item_name",
			"workstation",
			"status",
			"is_paused",
			"for_quantity",
			"total_completed_qty",
			"process_loss_qty",
			"sequence_id",
		],
		order_by="sequence_id asc, creation asc",
		limit_page_length=500,
	)
	if not job_cards:
		return []

	names = [jc.name for jc in job_cards]
	open_logs = set(
		frappe.get_all(
			"Job Card Time Log",
			filters={
				"parenttype": "Job Card",
				"parent": ("in", names),
				"from_time": ("is", "set"),
				"to_time": ("is", "not set"),
			},
			pluck="parent",
		)
	)
	started = set(
		frappe.get_all(
			"Job Card Time Log",
			filters={"parenttype": "Job Card", "parent": ("in", names), "from_time": ("is", "set")},
			pluck="parent",
			distinct=True,
		)
	)
	open_entries = {
		row.workstation: row
		for row in frappe.get_all(
			"Downtime Entry",
			filters={"status": "Open", "workstation": ("in", list({jc.workstation for jc in job_cards}))},
			fields=["name", "workstation", "job_card", "from_time", "downtime_reason", "category"],
		)
	}

	now = now_datetime()
	for jc in job_cards:
		ws = workstations[jc.workstation]
		jc.workstation_name = ws.workstation_name or ws.name
		jc.plant_floor = ws.plant_floor
		done_qty = flt(jc.total_completed_qty) + flt(jc.process_loss_qty)
		running = jc.name in open_logs and not jc.is_paused

		if running:
			jc.state = "Running"
		elif jc.name not in started:
			jc.state = "Not Started"
		elif flt(jc.for_quantity) and done_qty >= flt(jc.for_quantity):
			jc.state = "To Submit"
		else:
			jc.state = "Paused"

		entry = open_entries.get(jc.workstation)
		if entry and (entry.job_card == jc.name or (running and not entry.job_card)):
			jc.state = "Stopped"
			jc.downtime_entry = entry.name
			jc.downtime_reason = entry.downtime_reason
			jc.minutes_stopped = int((now - get_datetime(entry.from_time)).total_seconds() // 60)

	job_cards.sort(key=lambda jc: (JOB_CARD_STATE_ORDER[jc.state], jc.plant_floor or "", jc.workstation))
	return job_cards


@frappe.whitelist()
def get_reasons() -> list[dict]:
	frappe.has_permission("Downtime Reason", "read", throw=True)
	return frappe.get_list(
		"Downtime Reason",
		filters={"disabled": 0},
		fields=["name", "category", "is_planned"],
		order_by="category asc, name asc",
		limit_page_length=0,
	)


@frappe.whitelist(methods=["POST"])
def start_downtime(workstation: str, reason: str, remarks: str | None = None, job_card: str | None = None):
	_check_workstation_access(workstation)
	frappe.has_permission("Downtime Entry", "create", throw=True)
	if not frappe.db.exists("Downtime Reason", {"name": reason, "disabled": 0}):
		frappe.throw(_("Pick a valid Downtime Reason"))

	entry = frappe.get_doc(
		{
			"doctype": "Downtime Entry",
			"workstation": workstation,
			"from_time": now_datetime(),
			"downtime_reason": reason,
			"remarks": remarks,
			"job_card": job_card,
		}
	)
	entry.insert()
	return {"name": entry.name, "status": entry.status}


@frappe.whitelist(methods=["POST"])
def stop_downtime(workstation: str, remarks: str | None = None):
	_check_workstation_access(workstation)
	name = frappe.db.get_value("Downtime Entry", {"workstation": workstation, "status": "Open"}, "name")
	if not name:
		frappe.throw(_("Workstation {0} has no open stop").format(frappe.bold(workstation)))

	entry = frappe.get_doc("Downtime Entry", name)
	# Any operator of this machine may resume it, even if a colleague on the previous shift
	# logged the stop (Downtime Entry write is otherwise limited to the owner for operators).
	if not (
		frappe.has_permission("Downtime Entry", "write", doc=entry)
		or "Shopfloor Operator" in frappe.get_roles()
	):
		frappe.throw(_("Not permitted to resume this machine"), frappe.PermissionError)

	# To Time must be after From Time, even for a stop resumed within the same second
	entry.to_time = max(now_datetime(), add_to_date(entry.from_time, seconds=1))
	if remarks:
		entry.remarks = "\n".join(filter(None, [entry.remarks, remarks]))
	entry.flags.ignore_permissions = True
	entry.save()
	return {"name": entry.name, "status": entry.status, "downtime": entry.downtime}


# ----- Number Cards (type "Custom") -----


@frappe.whitelist()
def get_todays_oee_card(filters=None):
	from oee_tracker.oee import get_live_oee

	frappe.has_permission("OEE Log", "read", throw=True)
	cache_key = f"oee_tracker:todays_oee:{today()}"
	value = frappe.cache.get_value(cache_key)
	if value is None:
		results = get_live_oee()
		value = flt(sum(r.oee for r in results) / len(results), 1) if results else 0
		frappe.cache.set_value(cache_key, value, expires_in_sec=300)
	return {"value": value, "fieldtype": "Percent"}


@frappe.whitelist()
def get_downtime_today_card(filters=None):
	frappe.has_permission("Downtime Entry", "read", throw=True)
	start = get_datetime(today())
	now = now_datetime()
	entries = frappe.get_list(
		"Downtime Entry",
		filters=[
			["from_time", "<", now],
			["to_time", "is", "not set"],
		],
		fields=["from_time", "to_time"],
		limit_page_length=0,
	) + frappe.get_list(
		"Downtime Entry",
		filters=[["from_time", "<", now], ["to_time", ">", start]],
		fields=["from_time", "to_time"],
		limit_page_length=0,
	)
	total = sum(
		overlap_minutes(get_datetime(e.from_time), get_datetime(e.to_time) if e.to_time else now, start, now)
		for e in entries
	)
	return {"value": flt(total, 0), "fieldtype": "Float"}


def has_app_permission() -> bool:
	"""Show the app on the desk Apps screen to anyone who can use the shop floor."""
	allowed = {
		"Shopfloor Operator",
		"Shopfloor Supervisor",
		"Maintenance User",
		"Manufacturing User",
		"Manufacturing Manager",
		"System Manager",
	}
	return bool(allowed.intersection(frappe.get_roles()))
