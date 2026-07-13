# Weekly Report Improvements

## Goal

Create a manual weekly report for a selected site or studio. The report should show the selected week plus the previous five weeks, and later support downloading the report as an image.

## Phases

### Phase 1: Backend Endpoint

Status: Complete

Implemented:

- Added `GET /api/data/analytics/reports/weekly/`.
- Added a weekly report payload that accepts `site`, `studio`, `date_from`, and `date_to`.
- Reuses existing six-week trend calculations from the weekly dashboard.
- Returns weekly rows with:
  - trial bookings
  - attended trials
  - converted clients
  - converted members
  - client conversion rate
  - member conversion rate
  - occupancy rate
  - matched attendance
  - scheduled capacity
  - scheduled classes
- Added a staff table for the full six-week report period with:
  - instructor
  - effective classes by week
  - assistances
  - capacity
  - occupancy rate
- Effective classes are scheduled classes with at least one matched attended visit; zero-attendance classes are excluded from the instructor load table.
- Added definitions for report fields so the frontend can present consistent labels/help text.
- Added regression coverage for the endpoint, six-week window, studio filtering, conversions, and staff totals.

Validation:

- `manage.py test analytics.tests.WeeklyReportEndpointTests`
- `manage.py check`

### Phase 2: Weekly Report Screen

Status: Ready for user review

Implemented:

- Added a dashboard page for Weekly Report at `/dashboard/weekly-report`.
- Added the Weekly Report card to the dashboard hub.
- Reused the same site, studio, week navigation, and advanced period filter patterns as the existing weekly dashboard pages.
- Added English and Spanish labels for the page, charts, metrics, and instructor table.
- Shows:
  - trial-class bar chart
  - conversion bar and conversion-rate line chart
  - occupancy percentage line chart
  - assistances and effective-classes bar chart
  - instructor table with one row per instructor and one column per week, where each weekly cell shows classes / assistances / occupancy

Pending:

- User visual review and requested adjustments.

Validation:

- `npm run lint` passes with existing dashboard-style hook dependency warnings.
- `npm run build` passes and includes `/dashboard/weekly-report`.

### Phase 3: Review And Adjustments

Status: In progress

Implemented:

- Trial chart now shows attended trials only.
- Occupancy chart now labels each point with its occupancy percentage.
- Assistances and effective classes are shown as separate charts.
- Single-metric charts now hide their legends; the conversion chart keeps its legend because it uses stacked categories.
- Occupancy chart now appears first, and all charts use larger matching half-width panels.
- Class-load chart now stacks effective classes and not-attended classes, with total booked classes represented by the combined bar height.
- Occupancy point labels now show one decimal place.
- Added an assistances-by-hour chart using matched attended visits grouped by scheduled class start hour across the six-week report window.
- Assistances-by-hour labels now use compact 12-hour labels and show every hour tick.

Pending:

- User visual review and any additional layout/metric adjustments.

### Phase 4: Download Capability

Status: In progress

Implemented:

- Added frontend PNG export using the rendered Weekly Report content.
- Export includes report title, scope, KPI cards, charts, and instructor table while excluding the export button itself.
- Weekly report chart animations are disabled and export waits for the report paint cycle before capture to avoid partial line-chart snapshots.
- Export temporarily rasterizes Recharts SVG charts into PNG images before capture, then restores the live charts, to prevent incomplete or misaligned chart rendering in the downloaded PNG.
- Occupancy dot markers remain visible during normal page viewing and are hidden only while preparing exported images.
- Downloaded report header now centers the Beness logo, selected studio/site name, report title, and selected week range without changing the normal page header layout.
- Chart animations remain enabled during normal page viewing and are disabled only while preparing the PNG export.
- Instructor weekly table cells now show only classes and assistances, without occupancy.

Pending:

- User validation of the generated image size and layout.
- Consider a dedicated download-only layout after validating the first PNG export behavior.

### Attendance Import Alignment

Status: In progress

Implemented:

- Created branch `feature/report-attendance-alignment` for attendance/report alignment changes.
- Confirmed that Weekly Report assistances use matched scheduled-class attendance while Attendance Report completed visits use raw attended visits.
- Compared Piantini and Bella Vista unmatched attendance in the local data. Bella Vista showed a larger group-class matching gap in late May and early June 2026.
- Added soft-removal tracking for attendance visits so a newer Mindbody attendance report can correct older overlapping report windows.
- Added file-hash tracking on imports so exact duplicate attendance files are skipped before creating another raw-row audit copy.
- Attendance imports now store their covered date range on `ReportImport`.
- When a newer attendance import covers a date/studio window, previously active visits missing from that file are marked inactive with `removed_reason = missing_from_latest_import`.
- If a later import contains a previously removed visit again, the visit is reactivated and its removal metadata is cleared.
- Updated dashboard/report/class-match queries to exclude inactive attendance visits from active analytics.
- Parked the attendance reconstruction, restore, and auto-class cleanup utilities behind `ENABLE_ATTENDANCE_RECONSTRUCTION=False`.
- Removed reconstruction, restore, and cleanup controls from the active Uploads page to avoid production data changes in this version.
- Attendance import schedule automation now rebuilds class matches only; it no longer creates expected scheduled classes from templates.
- Kept the protected maintenance utilities in code for a possible future controlled repair, but they are disabled by default and not exposed in the UI.

Validation:

- `manage.py test core_data.test_analytics_import_guards analytics.tests.WeeklyReportEndpointTests analytics.test_client_metrics`
- `manage.py test analytics.tests.WeeklyReportEndpointTests`
- `manage.py makemigrations --check --dry-run`
- `npm run build`
