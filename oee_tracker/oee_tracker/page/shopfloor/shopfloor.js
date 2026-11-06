// Operator screen: one tile per open Job Card. Tap a running card to log a stop, tap red to resume.

frappe.pages["shopfloor"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Shop Floor"),
		single_column: true,
	});
	wrapper.shopfloor = new ShopFloor(page, wrapper);
};

frappe.pages["shopfloor"].on_page_show = function (wrapper) {
	wrapper.shopfloor && wrapper.shopfloor.refresh();
};

const STORAGE_KEY = "oee_tracker_shopfloor_plant_floor";
const REFRESH_MS = 30 * 1000;

class ShopFloor {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.reasons = null;
		this.busy = false;

		this.$body = $(`<div class="shopfloor">
			<div class="shopfloor-legend text-muted small">
				<span class="legend-dot running"></span>${__("Running: tap to log a stop")}
				<span class="legend-dot stopped"></span>${__("Stopped: tap to resume")}
				<span class="legend-dot paused"></span>${__("Paused")}
				<span class="legend-dot not-started"></span>${__("Not Started")}
				<span class="legend-dot to-submit"></span>${__("Done, to submit")}
			</div>
			<div class="shopfloor-grid"></div>
		</div>`).appendTo(page.main);
		this.$grid = this.$body.find(".shopfloor-grid");

		this.plant_floor_field = page.add_field({
			fieldtype: "Link",
			fieldname: "plant_floor",
			label: __("Plant Floor"),
			options: "Plant Floor",
			default: this.get_saved_plant_floor(),
			change: () => {
				this.save_plant_floor(this.plant_floor_field.get_value());
				this.refresh();
			},
		});
		page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		page.add_menu_item(__("Job Cards"), () => frappe.set_route("List", "Job Card"));
		page.add_menu_item(__("Downtime Entries"), () => frappe.set_route("List", "Downtime Entry"));
		page.add_menu_item(__("OEE Tracker Workspace"), () => frappe.set_route("oee-tracker"));

		this.$grid.on("click", ".shopfloor-tile", (e) => {
			const name = $(e.currentTarget).attr("data-job-card");
			const jc = (this.job_cards || []).find((j) => j.name === name);
			if (!jc || this.busy) return;
			if (jc.state === "Stopped") this.show_resume_dialog(jc);
			else if (jc.state === "Running") this.show_reason_dialog(jc);
			else
				frappe.show_alert({
					message: __("{0} is {1}. Start it on the Job Card to log stops here.", [jc.name, __(jc.state)]),
					indicator: "orange",
				});
		});

		frappe.realtime.on("oee_workstation_status", () => this.refresh_soon());
		this.timer = setInterval(() => {
			if (frappe.get_route_str() === "shopfloor") this.refresh();
		}, REFRESH_MS);

		this.refresh();
	}

	get_saved_plant_floor() {
		try {
			return localStorage.getItem(STORAGE_KEY) || "";
		} catch (e) {
			return "";
		}
	}

	save_plant_floor(value) {
		try {
			localStorage.setItem(STORAGE_KEY, value || "");
		} catch (e) {
			// storage blocked: the filter just won't be remembered
		}
	}

	refresh_soon() {
		clearTimeout(this.refresh_timeout);
		this.refresh_timeout = setTimeout(() => this.refresh(), 500);
	}

	async refresh() {
		const job_cards = await frappe.xcall("oee_tracker.api.get_job_card_status", {
			plant_floor: this.plant_floor_field.get_value() || null,
		});
		this.job_cards = job_cards || [];
		this.render();
	}

	render() {
		if (!this.job_cards.length) {
			this.$grid.html(
				`<div class="text-muted shopfloor-empty">${__(
					"No open Job Cards. Check the Plant Floor filter or your Workstation permissions."
				)}</div>`
			);
			return;
		}
		const esc = frappe.utils.escape_html;
		const css = {
			Running: "running",
			Stopped: "stopped",
			Paused: "paused",
			"Not Started": "not-started",
			"To Submit": "to-submit",
		};
		this.$grid.html(
			this.job_cards
				.map((jc) => {
					const stopped = jc.state === "Stopped";
					const qty = `${format_number(jc.total_completed_qty || 0, null, 0)} / ${format_number(
						jc.for_quantity || 0,
						null,
						0
					)}`;
					const detail = stopped
						? `<div class="tile-minutes">${__("{0} min", [jc.minutes_stopped])}</div>
						   <div class="tile-reason">${esc(__(jc.downtime_reason || ""))}</div>`
						: `<div class="tile-state">${esc(jc.state === "To Submit" ? __("Done, to submit") : __(jc.state))}</div>`;
					return `<button class="shopfloor-tile ${css[jc.state]}" data-job-card="${esc(jc.name)}">
						<div class="tile-name">${esc(__(jc.operation || ""))}</div>
						<div class="tile-floor">${esc(jc.workstation_name)}${
						jc.plant_floor ? ` · ${esc(jc.plant_floor)}` : ""
					}</div>
						<div class="tile-meta">${esc(jc.name)} · ${esc(jc.work_order || "")}</div>
						<div class="tile-meta">${esc(jc.item_name || jc.production_item || "")} · ${qty}</div>
						${detail}
					</button>`;
				})
				.join("")
		);
	}

	async get_reasons() {
		if (!this.reasons) {
			this.reasons = await frappe.xcall("oee_tracker.api.get_reasons");
		}
		return this.reasons;
	}

	async show_reason_dialog(jc) {
		const reasons = await this.get_reasons();
		const esc = frappe.utils.escape_html;
		const by_category = {};
		reasons.forEach((r) => (by_category[r.category] = by_category[r.category] || []).push(r));

		const html = Object.keys(by_category)
			.map(
				(category) => `<div class="reason-group">
					<div class="reason-category">${esc(__(category))}</div>
					<div class="reason-buttons">
						${by_category[category]
							.map(
								(r) => `<button class="btn reason-btn ${r.is_planned ? "planned" : ""}"
									data-reason="${esc(r.name)}">${esc(__(r.name))}</button>`
							)
							.join("")}
					</div>
				</div>`
			)
			.join("");

		const dialog = new frappe.ui.Dialog({
			title: __("Why did {0} stop?", [`${jc.workstation_name} (${__(jc.operation || "")})`]),
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "reasons" }],
		});
		dialog.fields_dict.reasons.$wrapper.html(`<div class="shopfloor-reasons">${html}</div>`);
		dialog.fields_dict.reasons.$wrapper.on("click", ".reason-btn", (e) => {
			const reason = $(e.currentTarget).attr("data-reason");
			dialog.hide();
			this.call(
				"oee_tracker.api.start_downtime",
				{ workstation: jc.workstation, reason, job_card: jc.name },
				() =>
					frappe.show_alert({
						message: __("{0} stopped: {1}", [jc.workstation_name, __(reason)]),
						indicator: "red",
					})
			);
		});
		dialog.show();
	}

	show_resume_dialog(jc) {
		const dialog = new frappe.ui.Dialog({
			title: __("Resume {0}?", [`${jc.workstation_name} (${__(jc.operation || "")})`]),
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "info",
					options: `<p class="text-muted">${__("Stopped {0} min ago: {1}", [
						jc.minutes_stopped,
						frappe.utils.escape_html(__(jc.downtime_reason || "")),
					])}</p>`,
				},
				{ fieldtype: "Small Text", fieldname: "remarks", label: __("Remarks (optional)") },
			],
			primary_action_label: __("Resume"),
			primary_action: (values) => {
				dialog.hide();
				this.call(
					"oee_tracker.api.stop_downtime",
					{ workstation: jc.workstation, remarks: values.remarks || null },
					() => frappe.show_alert({ message: __("{0} running", [jc.workstation_name]), indicator: "green" })
				);
			},
		});
		dialog.get_primary_btn().addClass("btn-lg");
		dialog.show();
	}

	call(method, args, on_success) {
		this.busy = true;
		frappe
			.xcall(method, args)
			.then(() => {
				on_success && on_success();
				return this.refresh();
			})
			.finally(() => (this.busy = false));
	}
}
