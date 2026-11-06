"""Demo data: a full ERPNext manufacturing cycle on a small shirt factory, with OEE tracking.

	bench --site <site> execute oee_tracker.demo.create_demo_data
	bench --site <site> execute oee_tracker.demo.delete_demo_data

The cycle, in the order it happens on the shop floor:

	1. Masters        Plant Floors, Operations, Workstations (with ideal cycle times), Shifts,
	                  Items (raw materials + finished shirt), BOMs with a 4-step routing
	                  Cutting -> Stitching -> Overlocking -> Pressing (sequence 1..4)
	2. Opening stock  Material Receipt of fabric and buttons into Stores
	   Then for every shift of the last DAYS days, for each of the two stitching lines:
	3. Work Order     planned for the shift, submitted (ERPNext creates one Job Card per operation)
	4. Transfer       Material Transfer for Manufacture, Stores -> Work In Progress
	5. Downtime       machine stops during the shift, linked to the Job Card and Work Order they hit
	6. Job Cards      completed in routing sequence: time logs, good qty, process loss, submitted
	7. Manufacture    Stock Entry for the pressed (finished) shirts into Finished Goods
	8. Close          the Work Order is closed (short-closed if output fell below plan)
	9. OEE            OEE Logs are built per workstation, shift and day

The shift that is running right now is left in progress: its Cutting Job Card is being worked on
and two machines are stopped, so the operator screen shows live state.

Cutting, Overlocking and Pressing are shared by both lines: line A uses them in the first half of
a shift and line B in the second half. Each stitching line is dedicated to its own Work Order.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import frappe
from frappe.utils import add_days, flt, getdate, now_datetime, today

from oee_tracker.shift import ShiftWindow, get_shift_window

DAYS = 14
SEED = 7
ITEM_PREFIX = "OEE-DEMO"
FG_ITEM = f"{ITEM_PREFIX}-FORMAL-SHIRT"
RAW_MATERIALS = [
	# item_code, name, uom, qty per shirt, rate, HSN
	(f"{ITEM_PREFIX}-SHIRTING-FABRIC", "Demo Cotton Shirting Fabric", "Meter", 1.6, 180, "52081110"),
	(f"{ITEM_PREFIX}-BUTTON", "Demo Shirt Button", "Nos", 8, 2, "96062100"),
]

PLANT_FLOORS = ["Cutting Section", "Stitching Section", "Finishing Section"]
ROUTING = ["Cutting", "Stitching", "Overlocking", "Pressing"]

SHIFTS = [
	(
		"Day Shift",
		"06:00:00",
		"14:00:00",
		[("Tea", "09:30:00", "09:45:00"), ("Lunch", "11:30:00", "12:00:00")],
	),
	(
		"Evening Shift",
		"14:00:00",
		"22:00:00",
		[("Tea", "17:30:00", "17:45:00"), ("Dinner", "19:30:00", "20:00:00")],
	),
]


@dataclass
class Machine:
	name: str
	floor: str
	operation: str
	ideal_sec: float
	stops: tuple  # stops per shift (min, max)
	speed: tuple  # actual speed as a share of ideal
	scrap_pct: tuple
	shared: bool  # used by both lines (half a shift each)


MACHINES = [
	Machine(
		"CM-01 Cutting Machine", "Cutting Section", "Cutting", 22, (1, 3), (0.88, 0.96), (0.3, 1.0), True
	),
	Machine(
		"SL-01 Stitching Line", "Stitching Section", "Stitching", 45, (1, 3), (0.86, 0.94), (1.0, 2.5), False
	),
	Machine(
		"SL-02 Stitching Line", "Stitching Section", "Stitching", 45, (2, 5), (0.76, 0.88), (2.0, 5.0), False
	),
	Machine(
		"OL-01 Overlock Machine",
		"Stitching Section",
		"Overlocking",
		28,
		(1, 3),
		(0.86, 0.95),
		(0.5, 1.5),
		True,
	),
	Machine("SP-01 Steam Press", "Finishing Section", "Pressing", 27, (0, 2), (0.90, 0.97), (0.2, 0.8), True),
]
BY_NAME = {m.name: m for m in MACHINES}

# Production lines: each has its own stitching line and BOM; the other machines are shared
LINES = {
	"A": {"stitching": "SL-01 Stitching Line", "half": 0},
	"B": {"stitching": "SL-02 Stitching Line", "half": 1},
}
SHARED = {
	"Cutting": "CM-01 Cutting Machine",
	"Overlocking": "OL-01 Overlock Machine",
	"Pressing": "SP-01 Steam Press",
}

# Unplanned reasons: weight, duration range in minutes
STOP_REASONS = [
	("Machine Breakdown", 18, (15, 60)),
	("Setup / Changeover", 22, (10, 30)),
	("Waiting for Material", 18, (10, 35)),
	("Power Cut", 8, (5, 25)),
	("Operator Not Available", 10, (5, 20)),
	("Quality Issue", 10, (5, 15)),
	("Unplanned Maintenance", 8, (15, 40)),
	("Other", 6, (5, 15)),
]

# Machines stopped right now in the running shift: workstation, reason, minutes ago
OPEN_STOPS = [
	("SL-02 Stitching Line", "Machine Breakdown", 35),
	("CM-01 Cutting Machine", "Waiting for Material", 12),
]


@dataclass
class Stop:
	start: datetime
	end: datetime | None
	reason: str
	remarks: str | None = None
	planned: bool = False
	created: bool = False


@dataclass
class Segment:
	"""A stretch of one machine's shift that belongs to one Work Order."""

	machine: Machine
	start: datetime
	end: datetime
	stops: list[Stop] = field(default_factory=list)
	run_minutes: float = 0.0
	capacity: int = 0


# ---------------------------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------------------------


def create_demo_data(company: str | None = None):
	frappe.only_for("System Manager")
	if frappe.db.exists("Workstation", MACHINES[0].name):
		frappe.throw("Demo data already exists. Run oee_tracker.demo.delete_demo_data first.")

	company = (
		company or frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	ctx = frappe._dict(
		company=company,
		stores=f"Stores - {abbr}",
		wip=f"Work In Progress - {abbr}",
		fg=f"Finished Goods - {abbr}",
		rng=random.Random(SEED),
		now=now_datetime(),
	)
	start_date = getdate(add_days(today(), -(DAYS - 1)))

	log("1. Masters")
	create_masters(ctx)
	log("2. Opening stock")
	create_opening_stock(ctx, add_days(start_date, -1))
	frappe.db.commit()

	log("3-8. Shifts: work orders, material transfer, downtime, job cards, manufacture, close")
	for offset in range(DAYS):
		day = getdate(add_days(start_date, offset))
		for shift_name, *_ in SHIFTS:
			window = get_shift_window(shift_name, day)
			if window.start >= ctx.now:
				continue
			run_shift(ctx, window)
			frappe.db.commit()
		log(f"   {day} done")

	log("9. OEE Logs")
	from oee_tracker.oee import build_for_range

	build_for_range(start_date, today())
	frappe.db.commit()
	log(summary())


def log(message):
	print(message, flush=True)


# ---------------------------------------------------------------------------------------------
# 1-2. Masters and opening stock
# ---------------------------------------------------------------------------------------------


def create_masters(ctx, lines=None):
	for floor in PLANT_FLOORS:
		if not frappe.db.exists("Plant Floor", floor):
			frappe.get_doc({"doctype": "Plant Floor", "floor_name": floor, "company": ctx.company}).insert()

	for operation in ROUTING:
		if not frappe.db.exists("Operation", operation):
			frappe.get_doc({"doctype": "Operation", "name": operation}).insert(set_name=operation)

	for name, start, end, breaks in SHIFTS:
		if not frappe.db.exists("Shift Definition", name):
			frappe.get_doc(
				{
					"doctype": "Shift Definition",
					"shift_name": name,
					"start_time": start,
					"end_time": end,
					"breaks": [{"break_name": b, "from_time": f, "to_time": t} for b, f, t in breaks],
				}
			).insert()
	# The demo runs two shifts; the install-time "General Shift" would overlap them
	if frappe.db.exists("Shift Definition", "General Shift"):
		frappe.db.set_value("Shift Definition", "General Shift", "disabled", 1)
	frappe.db.set_single_value("OEE Settings", "default_shift", "Day Shift")
	frappe.db.set_single_value("OEE Settings", "qty_source", "Job Card")

	for m in MACHINES:
		frappe.get_doc(
			{
				"doctype": "Workstation",
				"workstation_name": m.name,
				"plant_floor": m.floor,
				"production_capacity": 1,
				"hour_rate": 250,
				"ideal_cycle_time_sec": m.ideal_sec,
			}
		).insert()

	for item_code, item_name, uom, _qty, rate, hsn in RAW_MATERIALS:
		make_item(item_code, item_name, "Raw Material", uom, rate, hsn)
	make_item(FG_ITEM, "Demo Formal Shirt", "Products", "Nos", 0, "62052000")

	ctx.boms = {}
	for line, info in LINES.items():
		if lines and line not in lines:
			continue
		workstation_for = {**SHARED, "Stitching": info["stitching"]}
		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": FG_ITEM,
				"company": ctx.company,
				"quantity": 1,
				"is_default": 1 if line == "A" else 0,
				"with_operations": 1,
				"rm_cost_as_per": "Valuation Rate",
				"items": [
					{"item_code": code, "qty": qty, "rate": rate}
					for code, _n, _u, qty, rate, _h in RAW_MATERIALS
				],
				"operations": [
					{
						"operation": op,
						"workstation": workstation_for[op],
						"time_in_mins": BY_NAME[workstation_for[op]].ideal_sec / 60,
						"sequence_id": idx,
					}
					for idx, op in enumerate(ROUTING, start=1)
				],
			}
		).insert()
		bom.submit()
		ctx.boms[line] = bom.name


def make_item(item_code, item_name, item_group, uom, rate, hsn):
	if frappe.db.exists("Item", item_code):
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": item_group if frappe.db.exists("Item Group", item_group) else "All Item Groups",
			"stock_uom": uom,
			"is_stock_item": 1,
			"include_item_in_manufacturing": 1,
			"valuation_rate": rate,
			"standard_rate": rate,
			# Required when India Compliance is installed
			"gst_hsn_code": hsn if frappe.db.exists("DocType", "GST HSN Code") else None,
		}
	).insert()


def create_opening_stock(ctx, posting_date, shirts=None, posting_time="08:00:00"):
	# Default: enough for every Work Order of the demo period with room to spare
	shirts = shirts or 3000 * DAYS
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"company": ctx.company,
			"set_posting_time": 1,
			"posting_date": posting_date,
			"posting_time": posting_time,
			"remarks": "OEE demo: opening stock of raw materials",
			"items": [
				{"item_code": code, "qty": qty * shirts, "t_warehouse": ctx.stores, "basic_rate": rate}
				for code, _n, _u, qty, rate, _h in RAW_MATERIALS
			],
		}
	).insert()
	se.submit()


# ---------------------------------------------------------------------------------------------
# 3-8. One shift of production
# ---------------------------------------------------------------------------------------------


def run_shift(ctx, window: ShiftWindow):
	rng = ctx.rng
	running = window.end > ctx.now
	end = min(window.end, ctx.now - timedelta(minutes=2))

	if window.shift_date.weekday() == 6:  # Sunday: weekly off
		for m in MACHINES:
			add_downtime(m.name, Stop(window.start, end, "No Production Planned", "Weekly off", planned=True))
		return

	# Machine stops for the whole shift, then cut into per-Work-Order segments
	stops = {m.name: simulate_stops(ctx, m, window, end, running) for m in MACHINES}
	mid = window.start + (window.end - window.start) / 2
	segments = {}  # (line, operation) -> Segment
	for line, info in LINES.items():
		for op in ROUTING:
			m = BY_NAME[info["stitching"]] if op == "Stitching" else BY_NAME[SHARED[op]]
			if m.shared:
				seg_start, seg_end = (window.start, mid) if info["half"] == 0 else (mid, window.end)
			else:
				seg_start, seg_end = window.start, window.end
			seg_end = min(seg_end, end)
			if seg_end <= seg_start:
				continue
			seg = Segment(m, seg_start, seg_end)
			seg.stops = [s for s in stops[m.name] if seg_start <= s.start < seg_end]
			available = window.productive_minutes(seg_start, seg_end)
			stopped = sum(window.productive_minutes(s.start, min(s.end or end, seg_end)) for s in seg.stops)
			seg.run_minutes = max(available - stopped, 0)
			seg.capacity = int(seg.run_minutes * 60 / m.ideal_sec * rng.uniform(*m.speed))
			segments[(line, op)] = seg

	for line in LINES:
		cutting = segments.get((line, "Cutting"))
		if not cutting:
			continue  # line B's half of the running shift has not started yet
		plan_qty = get_plan_qty(line, cutting, running)
		if plan_qty > 0:
			run_work_order(ctx, window, line, plan_qty, segments, running)

	# Stops outside any Work Order (e.g. on a line whose half of the shift has not started)
	for m in MACHINES:
		for stop in stops[m.name]:
			if not stop.created:
				add_downtime(m.name, stop)


def get_plan_qty(line, cutting, running):
	"""Planned shirts for the shift: a finished shift plans what was cut; the running shift plans
	what the line's stitching can make in a full shift."""
	stitching = BY_NAME[LINES[line]["stitching"]]
	return int(435 * 60 / stitching.ideal_sec * 0.9) if running else cutting.capacity


def simulate_stops(ctx, m: Machine, window: ShiftWindow, end: datetime, running: bool) -> list[Stop]:
	rng = ctx.rng
	stops, cursor = [], window.start

	if window.shift_date.weekday() == 0 and window.shift == "Day Shift":
		planned_end = cursor + timedelta(minutes=30)
		stops.append(Stop(cursor, planned_end, "Planned Maintenance", "Weekly preventive maintenance", True))
		cursor = planned_end

	open_stop = next((s for s in OPEN_STOPS if s[0] == m.name), None) if running else None
	limit = end
	if open_stop:
		limit = max(ctx.now - timedelta(minutes=open_stop[2]), window.start + timedelta(minutes=1))

	for _ in range(rng.randint(*m.stops)):
		reason, (low, high) = pick_reason(rng)
		duration = timedelta(minutes=rng.randint(low, high))
		latest_start = limit - duration
		if latest_start <= cursor + timedelta(minutes=10):
			break
		gap = (latest_start - cursor).total_seconds() / 60
		start = (cursor + timedelta(minutes=rng.uniform(10, min(gap, 10 + gap / 2)))).replace(
			second=0, microsecond=0
		)
		stops.append(Stop(start, start + duration, reason))
		cursor = start + duration

	if open_stop and limit < end:
		stops.append(
			Stop(limit.replace(microsecond=0), None, open_stop[1], "Demo: machine is stopped right now")
		)
	return stops


def pick_reason(rng):
	pick = rng.uniform(0, sum(w for _r, w, _d in STOP_REASONS))
	for reason, weight, duration in STOP_REASONS:
		pick -= weight
		if pick <= 0:
			return reason, duration
	return STOP_REASONS[-1][0], STOP_REASONS[-1][2]


def run_work_order(ctx, window, line, plan_qty, segments, running):
	from erpnext.manufacturing.doctype.work_order.work_order import close_work_order, make_stock_entry

	rng = ctx.rng
	label = f"{window.shift_date} {window.shift}, line {line}"

	# 3. Work Order (ERPNext creates the Job Cards on submit)
	wo = frappe.get_doc(
		{
			"doctype": "Work Order",
			"production_item": FG_ITEM,
			"bom_no": ctx.boms[line],
			"company": ctx.company,
			"qty": plan_qty,
			"planned_start_date": window.start,
			"source_warehouse": ctx.stores,
			"wip_warehouse": ctx.wip,
			"fg_warehouse": ctx.fg,
			"transfer_material_against": "Work Order",
		}
	)
	wo.set_work_order_operations()
	wo.insert()
	wo.submit()
	job_cards = {
		jc.operation: jc.name
		for jc in frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "operation"])
	}

	# 4. Raw materials to Work In Progress
	transfer = frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", plan_qty))
	post_at(transfer, window.start)
	transfer.remarks = f"OEE demo: material issue for {label}"
	transfer.insert()
	transfer.submit()

	# 5. Downtime, linked to the Job Card running on that machine at the time
	for op in ROUTING:
		seg = segments.get((line, op))
		if seg:
			for stop in seg.stops:
				add_downtime(seg.machine.name, stop, job_card=job_cards.get(op), work_order=wo.name)

	# 6. Job Cards in routing sequence; each step can only use what the previous step passed on
	available = plan_qty
	final_good = 0
	for op in ROUTING:
		seg = segments.get((line, op))
		if not seg:
			break
		jc = frappe.get_doc("Job Card", job_cards[op])
		processed = min(seg.capacity, available)
		scrap = 0 if running else round(processed * rng.uniform(*seg.machine.scrap_pct) / 100)
		good = processed - scrap

		jc.time_logs = []
		jc.append("time_logs", {"from_time": seg.start, "to_time": seg.end, "completed_qty": good})
		jc.remarks = f"OEE demo: {label}"
		if running:
			jc.save()  # the running shift has only reached Cutting; later steps are still open
			break
		# What this step could not reach stays pending, so only real scrap counts as process loss
		jc.pending_qty = max(flt(jc.for_quantity) - good - scrap, 0)
		jc.save()
		jc.submit()
		available = final_good = good

	if running:
		return

	# 7. Finished shirts into stock
	if final_good:
		manufacture = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", final_good))
		post_at(manufacture, window.end)
		manufacture.remarks = f"OEE demo: shirts finished in {label}"
		manufacture.insert()
		manufacture.submit()

	# 8. Close the Work Order (short-closed when output fell below plan)
	wo.reload()
	if wo.status not in ("Completed", "Closed"):
		close_work_order(wo.name, "Closed")


def post_at(stock_entry, at: datetime):
	stock_entry.set_posting_time = 1
	stock_entry.posting_date = at.date()
	stock_entry.posting_time = at.strftime("%H:%M:%S")


def add_downtime(workstation, stop: Stop, job_card=None, work_order=None):
	entry = frappe.get_doc(
		{
			"doctype": "Downtime Entry",
			"workstation": workstation,
			"from_time": stop.start,
			"to_time": stop.end,
			"downtime_reason": stop.reason,
			"remarks": stop.remarks,
			"job_card": job_card,
			"work_order": work_order,
		}
	)
	entry.flags.skip_shift_split = True  # the demo already keeps stops inside their shift
	entry.insert()
	stop.created = True
	return entry


# ---------------------------------------------------------------------------------------------
# Summary and clean-up
# ---------------------------------------------------------------------------------------------


def summary() -> str:
	ws = [m.name for m in MACHINES]
	work_orders = frappe.get_all("Work Order", filters={"production_item": FG_ITEM}, pluck="name") or [""]
	# Finished shirts actually received (Manufacture entries net of process loss)
	sle = frappe.qb.DocType("Stock Ledger Entry")
	produced = (
		frappe.qb.from_(sle)
		.select(frappe.query_builder.functions.Sum(sle.actual_qty))
		.where((sle.item_code == FG_ITEM) & (sle.is_cancelled == 0) & (sle.actual_qty > 0))
		.run()[0][0]
	)
	return (
		f"Demo data ready: {len([w for w in work_orders if w])} work orders, "
		f"{frappe.db.count('Job Card', {'work_order': ('in', work_orders)})} job cards, "
		f"{frappe.db.count('Stock Entry', {'remarks': ('like', 'OEE demo:%')})} stock entries, "
		f"{flt(produced):.0f} shirts produced, "
		f"{frappe.db.count('Downtime Entry', {'workstation': ('in', ws)})} downtime entries, "
		f"{frappe.db.count('OEE Log', {'workstation': ('in', ws)})} OEE logs."
	)


def delete_demo_data():
	"""Cancel and delete everything create_demo_data made, newest first."""
	frappe.only_for("System Manager")
	ws = [m.name for m in MACHINES]
	items = frappe.get_all("Item", filters={"name": ("like", f"{ITEM_PREFIX}-%")}, pluck="name") or [""]
	work_orders = frappe.get_all("Work Order", filters={"production_item": ("in", items)}, pluck="name")

	frappe.db.delete("Downtime Entry", {"workstation": ("in", ws)})
	frappe.db.delete("OEE Log", {"workstation": ("in", ws)})

	stock_entries = frappe.get_all(
		"Stock Entry",
		filters={"docstatus": ("<", 2), "remarks": ("like", "OEE demo:%")},
		pluck="name",
		order_by="posting_date desc, posting_time desc, creation desc",
	)
	log(f"Cancelling {len(stock_entries)} stock entries")
	for name in stock_entries:
		cancel_and_delete("Stock Entry", name)
	frappe.db.commit()

	for name in frappe.get_all(
		"Job Card",
		filters={"work_order": ("in", work_orders or [""])},
		pluck="name",
		order_by="creation desc",
	):
		cancel_and_delete("Job Card", name)
	for name in work_orders[::-1]:
		cancel_and_delete("Work Order", name)
	for name in frappe.get_all("BOM", filters={"item": ("in", items)}, pluck="name"):
		cancel_and_delete("BOM", name)
	frappe.db.commit()

	for item in items:
		if item:
			frappe.delete_doc("Item", item, force=True, ignore_permissions=True)
	for name in ws:
		frappe.delete_doc("Workstation", name, force=True, ignore_missing=True, ignore_permissions=True)
	for floor in PLANT_FLOORS:
		if not frappe.db.exists("Workstation", {"plant_floor": floor}):
			frappe.delete_doc("Plant Floor", floor, force=True, ignore_missing=True, ignore_permissions=True)
	for operation in ROUTING:
		if not frappe.db.exists("BOM Operation", {"operation": operation}):
			frappe.delete_doc(
				"Operation", operation, force=True, ignore_missing=True, ignore_permissions=True
			)
	for name, *_ in SHIFTS:
		frappe.delete_doc("Shift Definition", name, force=True, ignore_missing=True, ignore_permissions=True)
	if frappe.db.exists("Shift Definition", "General Shift"):
		frappe.db.set_value("Shift Definition", "General Shift", "disabled", 0)
		frappe.db.set_single_value("OEE Settings", "default_shift", "General Shift")

	frappe.db.commit()
	log("Demo data deleted.")


def cancel_and_delete(doctype, name):
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		if doctype == "Work Order" and doc.status in ("Closed", "Stopped"):
			# ERPNext will not cancel a closed Work Order; reopen it first
			frappe.db.set_value("Work Order", name, "status", "Not Started", update_modified=False)
			doc.reload()
		doc.flags.ignore_links = True
		doc.flags.ignore_permissions = True
		doc.cancel()
	frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)


# ---------------------------------------------------------------------------------------------
# One complete transaction
# ---------------------------------------------------------------------------------------------

# One Work Order of 450 shirts on line A during a Day Shift (06:00-14:00, breaks 09:30-09:45 and
# 11:30-12:00). Each operation works its own part of the shift, in routing order; outside that
# the machine has no work, which is logged as a planned "No Production Planned" stop so OEE only
# measures the time the machine was meant to run.
#   operation: (workstation, start, end, processed qty, scrap, [unplanned stops: reason, from, to])
SINGLE_CYCLE_QTY = 450
SINGLE_CYCLE = {
	"Cutting": (
		"CM-01 Cutting Machine",
		"06:00",
		"09:30",
		450,
		3,
		[("Setup / Changeover", "06:00", "06:15")],
	),
	"Stitching": (
		"SL-01 Stitching Line",
		"06:30",
		"14:00",
		438,
		8,
		[("Machine Breakdown", "10:05", "10:40"), ("Waiting for Material", "12:40", "12:52")],
	),
	"Overlocking": (
		"OL-01 Overlock Machine",
		"09:45",
		"14:00",
		430,
		3,
		[("Quality Issue", "10:50", "11:00")],
	),
	"Pressing": ("SP-01 Steam Press", "10:15", "14:00", 427, 1, []),
}


def create_single_cycle(company: str | None = None):
	"""BOM -> Work Order -> material transfer -> Job Cards (in sequence, with downtime) ->
	Manufacture -> close -> OEE Logs, for one Work Order."""
	from erpnext.manufacturing.doctype.work_order.work_order import close_work_order, make_stock_entry

	from oee_tracker.oee import build_for_date

	frappe.only_for("System Manager")
	if frappe.db.exists("Workstation", MACHINES[0].name):
		frappe.throw("Demo data already exists. Run oee_tracker.demo.delete_demo_data first.")

	company = (
		company or frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name")[0]
	)
	abbr = frappe.get_cached_value("Company", company, "abbr")
	ctx = frappe._dict(
		company=company,
		stores=f"Stores - {abbr}",
		wip=f"Work In Progress - {abbr}",
		fg=f"Finished Goods - {abbr}",
	)

	# Today's Day Shift if it is over, otherwise yesterday's (skipping Sunday, the weekly off)
	day = getdate(today())
	if now_datetime() < datetime.combine(day, datetime.strptime("14:00", "%H:%M").time()):
		day = getdate(add_days(day, -1))
	if day.weekday() == 6:
		day = getdate(add_days(day, -1))
	at = lambda hhmm: datetime.combine(day, datetime.strptime(hhmm, "%H:%M").time())  # noqa: E731
	created = []

	log("Step 1. Masters: plant floors, operations, shifts, workstations, items, BOM")
	create_masters(ctx, lines=["A"])
	bom = ctx.boms["A"]
	created.append(("BOM", bom))

	log("Step 2. Opening stock of raw materials")
	create_opening_stock(ctx, day, shirts=SINGLE_CYCLE_QTY + 50, posting_time="05:30:00")
	created.append(
		("Stock Entry", frappe.db.get_value("Stock Entry", {"remarks": ("like", "OEE demo: opening%")}))
	)

	log("Step 3. Work Order (submitting it creates one Job Card per operation)")
	wo = frappe.get_doc(
		{
			"doctype": "Work Order",
			"production_item": FG_ITEM,
			"bom_no": bom,
			"company": ctx.company,
			"qty": SINGLE_CYCLE_QTY,
			"planned_start_date": at("06:00"),
			"source_warehouse": ctx.stores,
			"wip_warehouse": ctx.wip,
			"fg_warehouse": ctx.fg,
			"transfer_material_against": "Work Order",
		}
	)
	wo.set_work_order_operations()
	wo.insert()
	wo.submit()
	created.append(("Work Order", wo.name))
	job_cards = {
		jc.operation: jc.name
		for jc in frappe.get_all("Job Card", filters={"work_order": wo.name}, fields=["name", "operation"])
	}

	log("Step 4. Material Transfer for Manufacture: Stores -> Work In Progress")
	transfer = frappe.get_doc(
		make_stock_entry(wo.name, "Material Transfer for Manufacture", SINGLE_CYCLE_QTY)
	)
	post_at(transfer, at("06:00"))
	transfer.remarks = f"OEE demo: material issue for {wo.name}"
	transfer.insert()
	transfer.submit()
	created.append(("Stock Entry", transfer.name))

	log("Step 5. Downtime Entries, linked to the Job Card they interrupted")
	shift_start, shift_end = at("06:00"), at("14:00")
	for op, (workstation, start, end, _qty, _scrap, stops) in SINGLE_CYCLE.items():
		for reason, f, t in stops:
			entry = add_downtime(workstation, Stop(at(f), at(t), reason), job_cards[op], wo.name)
			created.append(("Downtime Entry", entry.name))
		# No work for this machine outside its part of the shift: a planned stop, not a loss
		if at(start) > shift_start:
			add_downtime(
				workstation,
				Stop(shift_start, at(start), "No Production Planned", f"No work until {op} starts", True),
			)
		if at(end) < shift_end:
			add_downtime(
				workstation,
				Stop(at(end), shift_end, "No Production Planned", f"{op} finished for {wo.name}", True),
			)
	# Machines that are not part of this Work Order had no work all shift
	for m in MACHINES:
		if m.name not in {v[0] for v in SINGLE_CYCLE.values()}:
			add_downtime(
				m.name,
				Stop(shift_start, shift_end, "No Production Planned", "Not used in this Work Order", True),
			)

	log("Step 6. Job Cards completed in routing sequence")
	final_good = 0
	for op in ROUTING:
		workstation, start, end, processed, scrap, _stops = SINGLE_CYCLE[op]
		good = processed - scrap
		jc = frappe.get_doc("Job Card", job_cards[op])
		jc.time_logs = []
		jc.append("time_logs", {"from_time": at(start), "to_time": at(end), "completed_qty": good})
		jc.pending_qty = max(flt(jc.for_quantity) - good - scrap, 0)
		jc.remarks = f"OEE demo: {op} on {workstation}"
		jc.save()
		jc.submit()
		final_good = good
		created.append(("Job Card", f"{jc.name}  ({op}: {good} good, {scrap} scrap)"))

	log("Step 7. Manufacture: finished shirts into Finished Goods")
	manufacture = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", final_good))
	post_at(manufacture, shift_end)
	manufacture.remarks = f"OEE demo: shirts finished for {wo.name}"
	manufacture.insert()
	manufacture.submit()
	created.append(("Stock Entry", manufacture.name))

	log("Step 8. Close the Work Order")
	wo.reload()
	if wo.status not in ("Completed", "Closed"):
		close_work_order(wo.name, "Closed")

	log("Step 9. OEE Logs for the shift")
	build_for_date(day, [m.name for m in MACHINES])
	for name in frappe.get_all("OEE Log", filters={"posting_date": day}, pluck="name"):
		created.append(("OEE Log", name))

	frappe.db.commit()
	log("\nCreated:")
	for doctype, name in created:
		log(f"  {doctype:15} {name}")
