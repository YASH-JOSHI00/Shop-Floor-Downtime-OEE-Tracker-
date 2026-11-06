// Copyright (c) 2026, yashjoshi and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shift Definition", {
	refresh(frm) {
		frm.set_intro(
			frm.doc.end_time && frm.doc.start_time && frm.doc.end_time < frm.doc.start_time
				? __("This shift runs past midnight and ends on the next day.")
				: ""
		);
	},
});
