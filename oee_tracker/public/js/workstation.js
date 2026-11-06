// Adds OEE shortcuts to the standard Workstation form (wired through doctype_js in hooks.py)

frappe.ui.form.on("Workstation", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(
			__("OEE Summary"),
			() => frappe.set_route("query-report", "OEE Summary", { workstation: frm.doc.name }),
			__("OEE")
		);
		frm.add_custom_button(
			__("Downtime Pareto"),
			() => frappe.set_route("query-report", "Downtime Pareto", { workstation: frm.doc.name }),
			__("OEE")
		);
		frm.add_custom_button(
			__("Downtime Entries"),
			() => frappe.set_route("List", "Downtime Entry", { workstation: frm.doc.name }),
			__("OEE")
		);
		if (frm.doc.current_status === "Stopped") {
			frm.set_intro(__("This machine is stopped right now."), "red");
		}
	},
});
