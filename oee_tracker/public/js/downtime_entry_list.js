frappe.listview_settings["Downtime Entry"] = Object.assign(frappe.listview_settings["Downtime Entry"] || {}, {
	add_fields: ["status", "category", "is_planned"],
	get_indicator(doc) {
		if (doc.status === "Open") return [__("Open"), "red", "status,=,Open"];
		if (doc.is_planned) return [__("Planned"), "blue", "is_planned,=,1"];
		return [__("Closed"), "green", "status,=,Closed"];
	},
});
