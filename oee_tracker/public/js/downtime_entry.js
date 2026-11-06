// Form script for the standard Downtime Entry (wired through doctype_js in hooks.py)

frappe.ui.form.on("Downtime Entry", {
	setup(frm) {
		frm.set_query("downtime_reason", () => ({ filters: { disabled: 0 } }));
		frm.set_query("job_card", () => ({
			filters: frm.doc.workstation
				? { workstation: frm.doc.workstation, docstatus: ["<", 2] }
				: { docstatus: ["<", 2] },
		}));
	},

	refresh(frm) {
		if (frm.doc.status === "Open" && !frm.is_new()) {
			frm.dashboard.set_headline_alert(
				__("Machine stopped since {0}", [frappe.datetime.str_to_user(frm.doc.from_time)]),
				"red"
			);
			frm.add_custom_button(__("Resume Machine"), () => {
				frm.set_value("to_time", frappe.datetime.now_datetime());
				frm.save();
			}).addClass("btn-primary");
		}
	},

	job_card(frm) {
		if (!frm.doc.job_card) return;
		frappe.db
			.get_value("Job Card", frm.doc.job_card, ["work_order", "workstation"])
			.then(({ message }) => {
				if (!message) return;
				frm.set_value("work_order", message.work_order);
				if (!frm.doc.workstation) frm.set_value("workstation", message.workstation);
			});
	},
});
