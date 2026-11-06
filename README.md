### OEE Tracker

Shop floor downtime capture and OEE (Availability × Performance × Quality) for ERPNext.
It extends the standard **Downtime Entry** through custom fields, property setters and
`doc_events`. No ERPNext core files are edited.

### What it adds

| Area | Details |
| --- | --- |
| DocTypes | Downtime Reason, Shift Definition (+ Shift Break), OEE Log, OEE Settings (+ OEE Alert Role) |
| Custom fields | Downtime Entry: `downtime_reason`, `category`, `is_planned`, `status` (Open/Closed), `shift`, `job_card`, `work_order`. Workstation: `ideal_cycle_time_sec`, `default_shift`, `current_status`. Job Card: `downtime_minutes` |
| Operator screen | `/app/shopfloor`: a tile per machine. Tap green to log a stop, tap red to resume. Updates live and also polls every 30 s |
| Reports | Downtime Pareto, Downtime Register, OEE Summary, MTTR and MTBF, Shift Comparison |
| Workspace | **OEE Tracker**: number cards, OEE trend, top reasons, OEE by workstation |
| Scheduler | Hourly long-stop alerts. Daily at 07:00 it builds yesterday's OEE Logs and emails the summary |
| Roles | Shopfloor Operator, Shopfloor Supervisor (reuses ERPNext's Maintenance User) |

### How OEE is computed

Per workstation, per shift, per day (stored in **OEE Log**):

- Planned production time = shift minutes − breaks − planned downtime
- Run time = planned production time − unplanned downtime
- Availability = run time ÷ planned production time
- Performance = ideal cycle time × total qty ÷ run time (capped at 100 % and flagged)
- Quality = good qty ÷ total qty

Quantities come from Job Card time logs, with process loss counted as rejected. If a site
doesn't use Job Cards, set **OEE Settings → Take Quantities From = Work Order** to use
Manufacture Stock Entries instead.

A workstation runs its **Default Shift** if one is set. Otherwise it runs every enabled
Shift Definition. Stops that cross a shift change are split at the boundary. Editing an
entry after its OEE Log was built re-runs that day in the background. **OEE Settings** also
has a button to rebuild any date range.

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch main
bench --site <site> install-app oee_tracker
```

Install creates the custom fields, permissions, a default reason list, a "General Shift"
and dashboard widgets. It also maps old `stop_reason` values to Downtime Reasons.

After installing:

1. Set **Ideal Cycle Time** (and optionally **Default Shift**) on each Workstation.
2. Adjust Shift Definitions and Downtime Reasons.
3. Give operators the *Shopfloor Operator* role. Use User Permissions on Workstation to limit which machines each one sees.

### Demo data

To try the app on a development site, generate two weeks of history from a full manufacturing
cycle: Items and a 4-step BOM routing (Cutting, Stitching, Overlocking, Pressing), opening stock,
then for every shift a Work Order, material transfer, Downtime Entries linked to Job Cards, Job
Cards completed in sequence, a Manufacture entry, and a closed Work Order. Finally it builds the OEE Logs.

```bash
bench --site <site> execute oee_tracker.demo.create_demo_data
bench --site <site> execute oee_tracker.demo.delete_demo_data   # removes it again
```

### Tests

```bash
bench --site <test-site> run-tests --app oee_tracker
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/oee_tracker
pre-commit install
```

### License

mit
