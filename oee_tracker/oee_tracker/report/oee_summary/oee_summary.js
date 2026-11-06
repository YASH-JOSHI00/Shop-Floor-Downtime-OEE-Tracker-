// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.query_reports["OEE Summary"] = {
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
		{ fieldname: "shift", label: __("Shift"), fieldtype: "Link", options: "Shift Definition" },
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options: ["Workstation and Date", "Workstation", "Date", "Shift Log"],
			default: "Workstation and Date",
		},
	],
	onload(report) {
		report.page.add_inner_button(__("OEE Logs"), () => frappe.set_route("List", "OEE Log"));
		frappe.db.get_single_value("OEE Settings", "oee_target").then((target) => {
			frappe.query_report.oee_target = target || 85;
		});
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "oee" && data && data.oee != null) {
			const target = frappe.query_report.oee_target || 85;
			value = `<b class="${data.oee >= target ? "text-success" : "text-danger"}">${value}</b>`;
		}
		return value;
	},
};
