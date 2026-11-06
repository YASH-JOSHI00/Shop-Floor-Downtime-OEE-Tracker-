"""Long-stop alerts (hourly) and the daily OEE summary email."""

import frappe
from frappe import _
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.utils import add_days, add_to_date, flt, format_datetime, get_url_to_form, getdate, now_datetime

from oee_tracker.oee import get_workstations


def get_settings():
	return frappe.get_cached_doc("OEE Settings")


def get_users_with_roles(roles) -> list[str]:
	roles = [r for r in set(roles) if r]
	if not roles:
		return []
	has_role = frappe.qb.DocType("Has Role")
	user = frappe.qb.DocType("User")
	return (
		frappe.qb.from_(has_role)
		.join(user)
		.on(has_role.parent == user.name)
		.select(user.name)
		.distinct()
		.where(
			(has_role.parenttype == "User")
			& has_role.role.isin(roles)
			& (user.enabled == 1)
			& (user.user_type == "System User")
			& user.name.notin(["Administrator", "Guest"])
		)
		.run(pluck=True)
	)


def check_long_stops():
	"""Hourly: alert on open stops longer than the threshold, once per stop."""
	settings = get_settings()
	threshold = settings.alert_threshold_minutes or 30
	cutoff = add_to_date(now_datetime(), minutes=-threshold)
	extra_roles = [row.role for row in settings.alert_roles]

	entries = frappe.get_all(
		"Downtime Entry",
		filters={"status": "Open", "alert_sent": 0, "from_time": ("<=", cutoff)},
		fields=["name", "workstation", "from_time", "downtime_reason", "category", "remarks"],
	)
	for entry in entries:
		notify_role = frappe.get_cached_value("Downtime Reason", entry.downtime_reason, "notify_role")
		recipients = get_users_with_roles([notify_role, *extra_roles])
		if recipients:
			send_long_stop_alert(entry, recipients, threshold)
		frappe.db.set_value("Downtime Entry", entry.name, "alert_sent", 1, update_modified=False)


def send_long_stop_alert(entry, recipients: list[str], threshold: int):
	minutes = int((now_datetime() - entry.from_time).total_seconds() // 60)
	subject = _("{0} stopped for {1} min: {2}").format(entry.workstation, minutes, entry.downtime_reason)
	message = _(
		"Workstation <b>{0}</b> has been stopped since {1} ({2} minutes, alert threshold {3} minutes).<br>"
		"Reason: <b>{4}</b> ({5})<br>{6}<br><a href='{7}'>Open Downtime Entry {8}</a>"
	).format(
		entry.workstation,
		format_datetime(entry.from_time),
		minutes,
		threshold,
		entry.downtime_reason,
		_(entry.category or ""),
		frappe.utils.escape_html(entry.remarks or ""),
		get_url_to_form("Downtime Entry", entry.name),
		entry.name,
	)

	enqueue_create_notification(
		recipients,
		{
			"type": "Alert",
			"document_type": "Downtime Entry",
			"document_name": entry.name,
			"subject": subject,
			"email_content": message,
			"from_user": "Administrator",
		},
	)
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		reference_doctype="Downtime Entry",
		reference_name=entry.name,
	)


def get_consecutive_below_target(workstation: str, posting_date, days: int, target: float) -> bool:
	"""True if the workstation's daily average OEE was below target on each of the last `days` days."""
	if days < 1:
		return False
	log = frappe.qb.DocType("OEE Log")
	from_date = add_days(posting_date, -(days - 1))
	rows = (
		frappe.qb.from_(log)
		.select(log.posting_date, frappe.query_builder.functions.Avg(log.oee).as_("oee"))
		.where(
			(log.workstation == workstation)
			& (log.posting_date >= from_date)
			& (log.posting_date <= posting_date)
		)
		.groupby(log.posting_date)
		.run(as_dict=True)
	)
	return len(rows) == days and all(flt(r.oee) < target for r in rows)


def get_daily_summary(posting_date) -> dict:
	settings = get_settings()
	target = flt(settings.oee_target) or 85
	days = settings.below_target_days or 3
	posting_date = getdate(posting_date)

	logs = frappe.get_all(
		"OEE Log",
		filters={"posting_date": posting_date},
		fields=[
			"workstation",
			"shift",
			"availability",
			"performance",
			"quality",
			"oee",
			"unplanned_downtime",
			"planned_downtime",
			"downtime_count",
			"is_flagged",
			"remarks",
		],
		order_by="workstation asc, shift_start asc",
	)
	below_target = [
		ws
		for ws in sorted({log.workstation for log in logs})
		if get_consecutive_below_target(ws, posting_date, days, target)
	]

	# Operators not logging stops is the biggest adoption risk: list machines with none in 7 days
	logged = set(
		frappe.get_all(
			"Downtime Entry",
			filters={"from_time": (">=", add_days(posting_date, -6)), "workstation": ("is", "set")},
			pluck="workstation",
			distinct=True,
		)
	)
	no_stops = [ws for ws in get_workstations() if ws not in logged]

	plant_oee = sum(flt(log.oee) for log in logs) / len(logs) if logs else 0
	return {
		"posting_date": posting_date,
		"logs": logs,
		"plant_oee": flt(plant_oee, 1),
		"target": target,
		"days": days,
		"below_target": below_target,
		"no_stops": no_stops,
		"total_unplanned": flt(sum(flt(log.unplanned_downtime) for log in logs), 0),
	}


def send_daily_summary(posting_date):
	settings = get_settings()
	if not settings.send_daily_summary:
		return
	recipients = get_users_with_roles([row.role for row in settings.summary_roles])
	if not recipients:
		return

	context = get_daily_summary(posting_date)
	if not context["logs"]:
		return

	frappe.sendmail(
		recipients=recipients,
		subject=_("OEE Summary for {0}: {1}%").format(
			frappe.format(context["posting_date"], {"fieldtype": "Date"}), context["plant_oee"]
		),
		template="oee_daily_summary",
		args=context,
		header=[_("Daily OEE Summary"), "blue"],
	)
