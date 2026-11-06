// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.query_reports["Downtime Pareto"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{ fieldname: "workstation", label: __("Workstation"), fieldtype: "Link", options: "Workstation" },
		{ fieldname: "plant_floor", label: __("Plant Floor"), fieldtype: "Link", options: "Plant Floor" },
		{ fieldname: "shift", label: __("Shift"), fieldtype: "Link", options: "Shift Definition" },
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Reason", "Category"],
			default: "Reason",
		},
		{ fieldname: "include_planned", label: __("Include Planned Stops"), fieldtype: "Check", default: 0 },
	],
};
