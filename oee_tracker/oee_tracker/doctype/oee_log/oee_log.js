// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.ui.form.on("OEE Log", {
	refresh(frm) {
		if (frm.doc.is_flagged && frm.doc.remarks) {
			frm.dashboard.set_headline_alert(frm.doc.remarks, "orange");
		}
		frm.add_custom_button(__("Downtime Entries"), () => {
			frappe.route_options = {
				workstation: frm.doc.workstation,
				from_time: ["<", frm.doc.shift_end],
			};
			frappe.set_route("List", "Downtime Entry");
		});
	},
});
