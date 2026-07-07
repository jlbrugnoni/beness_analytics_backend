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

Status: Not started

Planned:

- Review field definitions with real data.
- Adjust labels, chart choices, sorting, and layout.
- Check mobile/desktop responsiveness.

### Phase 4: Download Capability

Status: Not started

Planned:

- Add report image download after the screen and information design are approved.
