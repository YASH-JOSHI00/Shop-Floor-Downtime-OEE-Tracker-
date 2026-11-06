import frappe


def make_shift(name, start, end, breaks=()):
	if frappe.db.exists("Shift Definition", name):
		frappe.delete_doc("Shift Definition", name, force=True)
	return frappe.get_doc(
		{
			"doctype": "Shift Definition",
			"shift_name": name,
			"start_time": start,
			"end_time": end,
			"breaks": [
				{"break_name": f"Break {i}", "from_time": f, "to_time": t} for i, (f, t) in enumerate(breaks)
			],
		}
	).insert()


def make_workstation(name, shift=None, ideal_cycle_time_sec=0):
	if frappe.db.exists("Workstation", name):
		frappe.db.delete("Downtime Entry", {"workstation": name})
		frappe.db.delete("OEE Log", {"workstation": name})
		frappe.delete_doc("Workstation", name, force=True)
	return frappe.get_doc(
		{
			"doctype": "Workstation",
			"workstation_name": name,
			"default_shift": shift,
			"ideal_cycle_time_sec": ideal_cycle_time_sec,
		}
	).insert()


def make_reason(name, category="Breakdown", is_planned=0, legacy="Machine malfunction"):
	if not frappe.db.exists("Downtime Reason", name):
		frappe.get_doc(
			{
				"doctype": "Downtime Reason",
				"reason_name": name,
				"category": category,
				"is_planned": is_planned,
				"legacy_stop_reason": legacy,
			}
		).insert()
	return name


def make_entry(workstation, from_time, to_time=None, reason="_Test OEE Breakdown", **kwargs):
	return frappe.get_doc(
		{
			"doctype": "Downtime Entry",
			"workstation": workstation,
			"from_time": from_time,
			"to_time": to_time,
			"downtime_reason": reason,
			**kwargs,
		}
	).insert()
