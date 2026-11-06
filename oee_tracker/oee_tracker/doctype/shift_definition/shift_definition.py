# Copyright (c) 2026, yashjoshi and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from oee_tracker.shift import minutes_between_times


class ShiftDefinition(Document):
	def validate(self):
		if self.start_time == self.end_time:
			frappe.throw(_("Start Time and End Time cannot be the same"))

		self.total_minutes = minutes_between_times(self.start_time, self.end_time)
		break_minutes = 0
		for row in self.breaks:
			row.minutes = minutes_between_times(row.from_time, row.to_time)
			break_minutes += row.minutes
		if break_minutes >= self.total_minutes:
			frappe.throw(
				_("Breaks ({0} min) cannot be longer than the shift ({1} min)").format(
					break_minutes, self.total_minutes
				)
			)
		self.break_minutes = break_minutes
		self.planned_minutes = self.total_minutes - break_minutes
