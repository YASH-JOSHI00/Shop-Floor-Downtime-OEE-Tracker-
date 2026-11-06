// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.ui.form.on("OEE Settings", {
	rebuild_oee_logs(frm) {
		if (frm.is_dirty()) {
			frappe.msgprint(__("Save the settings first"));
			return;
		}
		frappe.call({
			method: "oee_tracker.oee_tracker.doctype.oee_settings.oee_settings.rebuild_oee_logs",
			args: { from_date: frm.doc.rebuild_from_date, to_date: frm.doc.rebuild_to_date },
			freeze: true,
			callback: (r) => r.message && frappe.show_alert({ message: r.message, indicator: "blue" }),
		});
	},
});
