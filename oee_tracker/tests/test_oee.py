from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from oee_tracker.oee import compute_oee
from oee_tracker.shift import get_shift_window
from oee_tracker.tests.utils import make_entry, make_reason, make_shift, make_workstation

DAY = "2026-01-05"


def qty(total, good):
	return frappe._dict(total_qty=total, good_qty=good, rejected_qty=total - good)


class TestOEECalculation(IntegrationTestCase):
	def setUp(self):
		make_shift("_Test OEE Day", "08:00:00", "16:00:00", [("12:00:00", "13:00:00")])
		make_workstation("_Test OEE WS", shift="_Test OEE Day", ideal_cycle_time_sec=30)
		make_reason("_Test OEE Breakdown")
		make_reason("_Test OEE Planned", category="Other", is_planned=1, legacy="Other")
		self.window = get_shift_window("_Test OEE Day", DAY)

	def test_worked_example_from_plan(self):
		# 420 planned min, 42 min unplanned stop, 30 s x 680 units, 646 good -> OEE 76.9%
		make_entry("_Test OEE WS", f"{DAY} 09:00:00", f"{DAY} 09:42:00")
		with patch("oee_tracker.oee.get_quantities", return_value=qty(680, 646)):
			result = compute_oee("_Test OEE WS", self.window)

		self.assertEqual(result.planned_time, 420)
		self.assertEqual(result.run_time, 378)
		self.assertEqual(result.availability, 90)
		self.assertAlmostEqual(result.performance, 89.95, delta=0.01)
		self.assertEqual(result.quality, 95)
		self.assertAlmostEqual(result.oee, 76.9, delta=0.05)
		self.assertFalse(result.is_flagged)

	def test_planned_stop_reduces_planned_time_not_availability(self):
		make_entry("_Test OEE WS", f"{DAY} 14:00:00", f"{DAY} 15:00:00", reason="_Test OEE Planned")
		with patch("oee_tracker.oee.get_quantities", return_value=qty(100, 100)):
			result = compute_oee("_Test OEE WS", self.window)
		self.assertEqual(result.planned_time, 360)
		self.assertEqual(result.availability, 100)

	def test_downtime_during_break_is_not_counted(self):
		make_entry("_Test OEE WS", f"{DAY} 11:30:00", f"{DAY} 13:30:00")
		with patch("oee_tracker.oee.get_quantities", return_value=qty(100, 100)):
			result = compute_oee("_Test OEE WS", self.window)
		self.assertEqual(result.unplanned_downtime, 60)

	def test_performance_above_100_is_capped_and_flagged(self):
		with patch("oee_tracker.oee.get_quantities", return_value=qty(2000, 2000)):
			result = compute_oee("_Test OEE WS", self.window)
		self.assertEqual(result.performance, 100)
		self.assertTrue(result.is_flagged)

	def test_no_production_is_flagged(self):
		with patch("oee_tracker.oee.get_quantities", return_value=qty(0, 0)):
			result = compute_oee("_Test OEE WS", self.window)
		self.assertEqual(result.oee, 0)
		self.assertTrue(result.is_flagged)
