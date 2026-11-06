// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.query_reports["Shift Comparison"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{ fieldname: "workstation", label: __("Workstation"), fieldtype: "Link", options: "Workstation" },
		{ fieldname: "plant_floor", label: __("Plant Floor"), fieldtype: "Link", options: "Plant Floor" },
		{
			fieldname: "group_by",
			label: __("Compare"),
			fieldtype: "Select",
			options: ["Shift", "Operator"],
			default: "Shift",
		},
	],
};
