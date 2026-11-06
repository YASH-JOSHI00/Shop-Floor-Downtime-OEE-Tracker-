app_name = "oee_tracker"
app_title = "OEE Tracker"
app_publisher = "yashjoshi"
app_description = "Shop floor downtime capture and OEE tracking for ERPNext"
app_email = "yashkumarjoshi2002@gmail.com"
app_license = "mit"

required_apps = ["erpnext"]

# Landing page of the app: the "OEE Tracker" workspace
app_home = "/desk/oee-tracker"
app_logo_url = "/assets/oee_tracker/images/oee-tracker-logo.svg"
add_to_apps_screen = [
	{
		"name": app_name,
		"logo": app_logo_url,
		"title": app_title,
		"route": app_home,
		"has_permission": "oee_tracker.api.has_app_permission",
	}
]

# Installation
# ------------
after_install = "oee_tracker.install.after_install"
after_migrate = "oee_tracker.install.after_migrate"
before_uninstall = "oee_tracker.install.before_uninstall"

# Form scripts for standard ERPNext DocTypes (no core edits)
doctype_js = {
	"Downtime Entry": "public/js/downtime_entry.js",
	"Workstation": "public/js/workstation.js",
}
doctype_list_js = {
	"Downtime Entry": "public/js/downtime_entry_list.js",
}

# Document Events on the standard Downtime Entry
doc_events = {
	"Downtime Entry": {
		"validate": "oee_tracker.overrides.downtime_entry.validate",
		"on_update": "oee_tracker.overrides.downtime_entry.on_update",
		"on_trash": "oee_tracker.overrides.downtime_entry.on_trash",
	},
	"Job Card": {
		"on_update": "oee_tracker.overrides.job_card.notify_shopfloor",
		"on_submit": "oee_tracker.overrides.job_card.notify_shopfloor",
		"on_cancel": "oee_tracker.overrides.job_card.notify_shopfloor",
		"on_trash": "oee_tracker.overrides.job_card.notify_shopfloor",
	},
}

# Scheduled Tasks
scheduler_events = {
	"hourly": [
		"oee_tracker.alerts.check_long_stops",
	],
	"cron": {
		# Runs after the night shift ends: builds yesterday's OEE Logs and mails the summary
		"0 7 * * *": [
			"oee_tracker.oee.build_previous_day",
		],
	},
}

# Roles shipped by the app. "Maintenance User" already comes with ERPNext and is reused.
fixtures = [
	{
		"dt": "Role",
		"filters": [["name", "in", ["Shopfloor Operator", "Shopfloor Supervisor"]]],
	},
]
