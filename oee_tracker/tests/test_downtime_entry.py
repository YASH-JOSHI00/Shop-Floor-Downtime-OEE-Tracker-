import frappe
from frappe.tests import IntegrationTestCase

from oee_tracker import api
from oee_tracker.tests.utils import make_entry, make_reason, make_shift, make_workstation

DAY = "2026-01-05"


class TestDowntimeEntry(IntegrationTestCase):
	def setUp(self):
		make_shift("_Test OEE Day", "08:00:00", "16:00:00")
		make_workstation("_Test OEE WS", shift="_Test OEE Day", ideal_cycle_time_sec=30)
		make_reason("_Test OEE Breakdown")

	def ws_status(self):
		return frappe.db.get_value("Workstation", "_Test OEE WS", "current_status")

	def test_reason_details_and_legacy_stop_reason(self):
		entry = make_entry("_Test OEE WS", f"{DAY} 09:00:00", f"{DAY} 09:30:00")
		self.assertEqual(entry.status, "Closed")
		self.assertEqual(entry.category, "Breakdown")
		self.assertEqual(entry.stop_reason, "Machine malfunction")
		self.assertEqual(entry.shift, "_Test OEE Day")
		self.assertEqual(entry.downtime, 30)

	def test_open_and_close(self):
		entry = make_entry("_Test OEE WS", f"{DAY} 09:00:00")
		self.assertEqual(entry.status, "Open")
		self.assertEqual(self.ws_status(), "Stopped")

		entry.to_time = f"{DAY} 09:20:00"
		entry.save()
		self.assertEqual(entry.status, "Closed")
		self.assertEqual(self.ws_status(), "Running")

	def test_only_one_open_entry_per_workstation(self):
		make_entry("_Test OEE WS", f"{DAY} 09:00:00")
		with self.assertRaises(frappe.ValidationError):
			make_entry("_Test OEE WS", f"{DAY} 09:10:00")

	def test_split_at_shift_end(self):
		entry = make_entry("_Test OEE WS", f"{DAY} 15:00:00", f"{DAY} 17:00:00")
		self.assertEqual(str(entry.to_time), f"{DAY} 16:00:00")
		self.assertEqual(entry.downtime, 60)
		remainder = frappe.get_all(
			"Downtime Entry",
			filters={"workstation": "_Test OEE WS", "from_time": f"{DAY} 16:00:00"},
			fields=["to_time", "downtime", "shift"],
		)
		self.assertEqual(len(remainder), 1)
		self.assertEqual(remainder[0].downtime, 60)
		self.assertFalse(remainder[0].shift)

	def test_operator_screen_api(self):
		started = api.start_downtime("_Test OEE WS", "_Test OEE Breakdown")
		self.assertEqual(started["status"], "Open")
		self.assertEqual(self.ws_status(), "Stopped")

		tiles = {t.name: t for t in api.get_workstation_status()}
		self.assertEqual(tiles["_Test OEE WS"].status, "Stopped")

		stopped = api.stop_downtime("_Test OEE WS")
		self.assertEqual(stopped["name"], started["name"])
		self.assertEqual(self.ws_status(), "Running")

		with self.assertRaises(frappe.ValidationError):
			api.stop_downtime("_Test OEE WS")
