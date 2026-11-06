from datetime import datetime

from frappe.tests import IntegrationTestCase

from oee_tracker.shift import find_shift_window, get_shift_window, minutes_between_times
from oee_tracker.tests.utils import make_shift, make_workstation


class TestShift(IntegrationTestCase):
	def test_minutes_between_times(self):
		self.assertEqual(minutes_between_times("09:00:00", "17:30:00"), 510)
		self.assertEqual(minutes_between_times("22:00:00", "06:00:00"), 480)

	def test_shift_definition_totals(self):
		shift = make_shift(
			"_Test OEE Day", "08:00:00", "16:00:00", [("12:00:00", "12:45:00"), ("15:00:00", "15:15:00")]
		)
		self.assertEqual(shift.total_minutes, 480)
		self.assertEqual(shift.break_minutes, 60)
		self.assertEqual(shift.planned_minutes, 420)

	def test_overnight_window(self):
		make_shift("_Test OEE Night", "22:00:00", "06:00:00", [("02:00:00", "02:30:00")])
		window = get_shift_window("_Test OEE Night", "2026-01-05")
		self.assertEqual(window.start, datetime(2026, 1, 5, 22))
		self.assertEqual(window.end, datetime(2026, 1, 6, 6))
		self.assertEqual(window.breaks, [(datetime(2026, 1, 6, 2), datetime(2026, 1, 6, 2, 30))])
		self.assertEqual(window.total_minutes - window.break_minutes, 450)

	def test_find_shift_window_after_midnight(self):
		make_shift("_Test OEE Night", "22:00:00", "06:00:00")
		make_workstation("_Test OEE WS Night", shift="_Test OEE Night")
		window = find_shift_window("_Test OEE WS Night", "2026-01-06 02:00:00")
		self.assertEqual(window.shift_date, datetime(2026, 1, 5).date())
		self.assertIsNone(find_shift_window("_Test OEE WS Night", "2026-01-06 12:00:00"))
