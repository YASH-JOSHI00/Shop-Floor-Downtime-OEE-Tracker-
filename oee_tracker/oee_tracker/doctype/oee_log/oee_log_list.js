frappe.listview_settings["OEE Log"] = {
	add_fields: ["oee", "is_flagged"],
	get_indicator(doc) {
		if (doc.is_flagged) return [__("Flagged"), "orange", "is_flagged,=,1"];
		return [__("OK"), "green", "is_flagged,=,0"];
	},
};
