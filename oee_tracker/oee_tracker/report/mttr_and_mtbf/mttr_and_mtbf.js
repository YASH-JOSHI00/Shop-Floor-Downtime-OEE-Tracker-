// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.query_reports["MTTR and MTBF"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -3),
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
			fieldname: "category",
			label: __("Failure Category"),
			fieldtype: "Select",
			options: ["Breakdown", "Material", "Setup", "Power", "Manpower", "Quality", "Other"],
			default: "Breakdown",
		},
	],
};
