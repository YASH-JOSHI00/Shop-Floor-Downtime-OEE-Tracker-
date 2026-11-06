"""Shift calendar helpers shared by Downtime Entry logic, the OEE builder and reports.

A Shift Definition is a daily pattern (start/end time plus breaks). A shift "instance" is that
pattern on a given date; shifts whose end time is earlier than their start time end the next day.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import frappe
from frappe.utils import add_days, get_datetime, getdate, to_timedelta

DAY = timedelta(days=1)


@dataclass
class ShiftWindow:
	shift: str
	shift_date: date
	start: datetime
	end: datetime
	breaks: list[tuple[datetime, datetime]] = field(default_factory=list)

	@property
	def total_minutes(self) -> float:
		return minutes(self.start, self.end)

	@property
	def break_minutes(self) -> float:
		return sum(minutes(s, e) for s, e in self.breaks)

	def productive_minutes(self, start: datetime, end: datetime) -> float:
		"""Minutes of [start, end] that fall inside this shift and outside its breaks."""
		inside = overlap_minutes(start, end, self.start, self.end)
		if not inside:
			return 0.0
		in_breaks = sum(overlap_minutes(start, end, b_start, b_end) for b_start, b_end in self.breaks)
		return max(inside - in_breaks, 0.0)


def minutes(start: datetime, end: datetime) -> float:
	return (end - start).total_seconds() / 60


def overlap_minutes(a_start, a_end, b_start, b_end) -> float:
	start, end = max(a_start, b_start), min(a_end, b_end)
	return max(minutes(start, end), 0.0)


def minutes_between_times(from_time, to_time) -> float:
	"""Length of a time range in minutes; a range that wraps past midnight ends the next day."""
	delta = to_timedelta(to_time) - to_timedelta(from_time)
	if delta <= timedelta(0):
		delta += DAY
	return delta.total_seconds() / 60


def get_shift_window(shift: str, shift_date) -> ShiftWindow:
	doc = frappe.get_cached_doc("Shift Definition", shift)
	shift_date = getdate(shift_date)
	base = datetime.combine(shift_date, datetime.min.time())
	start = base + to_timedelta(doc.start_time)
	end = base + to_timedelta(doc.end_time)
	if end <= start:
		end += DAY

	breaks = []
	for row in doc.breaks:
		b_start = base + to_timedelta(row.from_time)
		if b_start < start:
			b_start += DAY
		b_end = b_start + timedelta(minutes=minutes_between_times(row.from_time, row.to_time))
		breaks.append((max(b_start, start), min(b_end, end)))

	return ShiftWindow(shift=shift, shift_date=shift_date, start=start, end=end, breaks=breaks)


def get_workstation_shifts(workstation: str) -> list[str]:
	"""Shifts a workstation runs: its Default Shift if set, otherwise every enabled shift."""
	default_shift = frappe.get_cached_value("Workstation", workstation, "default_shift")
	if default_shift:
		return [default_shift]
	shifts = frappe.get_all(
		"Shift Definition", filters={"disabled": 0}, pluck="name", order_by="start_time asc"
	)
	if not shifts:
		fallback = frappe.db.get_single_value("OEE Settings", "default_shift")
		shifts = [fallback] if fallback else []
	return shifts


def get_shift_windows_for_date(workstation: str, shift_date) -> list[ShiftWindow]:
	return [get_shift_window(shift, shift_date) for shift in get_workstation_shifts(workstation)]


def find_shift_window(workstation: str, at) -> ShiftWindow | None:
	"""The shift instance of `workstation` that contains the moment `at`.

	Checks the previous day too, so 02:00 belongs to last night's overnight shift.
	"""
	at = get_datetime(at)
	for day in (getdate(at), getdate(add_days(at, -1))):
		for window in get_shift_windows_for_date(workstation, day):
			if window.start <= at < window.end:
				return window
	return None


def get_next_boundary(workstation: str, start, end):
	"""First shift boundary strictly inside (start, end), or None.

	Inside a shift that is the shift's end; between shifts it is the next shift's start.
	"""
	start, end = get_datetime(start), get_datetime(end)
	window = find_shift_window(workstation, start)
	if window:
		return window.end if window.end < end else None

	day = getdate(start)
	while day <= getdate(end):
		starts = [w.start for w in get_shift_windows_for_date(workstation, day) if start < w.start < end]
		if starts:
			return min(starts)
		day = getdate(add_days(day, 1))
	return None
