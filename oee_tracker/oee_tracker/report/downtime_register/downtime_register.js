// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.query_reports["Downtime Register"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
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
		{
			fieldname: "downtime_reason",
			label: __("Downtime Reason"),
			fieldtype: "Link",
			options: "Downtime Reason",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: ["", "Breakdown", "Material", "Setup", "Power", "Manpower", "Quality", "Other"],
		},
		{ fieldname: "shift", label: __("Shift"), fieldtype: "Link", options: "Shift Definition" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Open", "Closed"] },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.status === "Open") {
			value = `<span class="text-danger">${value}</span>`;
		}
		return value;
	},
};
