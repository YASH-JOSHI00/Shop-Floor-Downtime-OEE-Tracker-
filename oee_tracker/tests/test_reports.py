import frappe
from frappe.desk.query_report import run
from frappe.tests import IntegrationTestCase

from oee_tracker.tests.utils import make_entry, make_reason, make_shift, make_workstation

REPORTS = {
	"Downtime Pareto": {"group_by": "Reason"},
	"Downtime Register": {},
	"OEE Summary": {"group_by": "Workstation and Date"},
	"MTTR and MTBF": {"category": "Breakdown"},
	"Shift Comparison": {"group_by": "Shift"},
}


class TestReports(IntegrationTestCase):
	def setUp(self):
		make_shift("_Test OEE Day", "08:00:00", "16:00:00")
		make_workstation("_Test OEE WS", shift="_Test OEE Day", ideal_cycle_time_sec=30)
		make_reason("_Test OEE Breakdown")
		make_entry("_Test OEE WS", "2026-01-05 09:00:00", "2026-01-05 09:30:00")
		make_entry("_Test OEE WS", "2026-01-05 10:00:00", "2026-01-05 10:10:00")

	def test_reports_run(self):
		for report, extra in REPORTS.items():
			filters = {"from_date": "2026-01-01", "to_date": "2026-01-31", **extra}
			result = run(report, filters=filters, ignore_prepared_report=True)
			self.assertIn("result", result, report)

	def test_pareto_totals(self):
		from oee_tracker.oee_tracker.report.downtime_pareto.downtime_pareto import execute

		_columns, data, *_ = execute(
			frappe._dict(from_date="2026-01-01", to_date="2026-01-31", workstation="_Test OEE WS")
		)
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0].count, 2)
		self.assertEqual(data[0].minutes, 40)
		self.assertEqual(data[0].cumulative, 100)

	def test_mttr(self):
		from oee_tracker.oee_tracker.report.mttr_and_mtbf.mttr_and_mtbf import execute

		_columns, data, *_ = execute(
			frappe._dict(from_date="2026-01-01", to_date="2026-01-31", workstation="_Test OEE WS")
		)
		self.assertEqual(data[0].failures, 2)
		self.assertEqual(data[0].mttr, 20)
