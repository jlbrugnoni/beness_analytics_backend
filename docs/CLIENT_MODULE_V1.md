# Client Module V1

## Purpose

The Client Module provides two connected views of client health:

1. A site or studio view for comparing, ranking, and segmenting clients.
2. An individual client view for understanding the attendance, purchases,
   membership history, preferences, and behavior behind those results.

The module must support both historical/lifetime analysis and recent scopes such
as a selected month or the last 4, 8, 12, or 16 weeks.

Raw imported records remain the source of truth. Calculated tables contain
rebuildable facts that make studio and site analysis fast.

## Development Workflow

- Development branch: `feature/client-module-v1`
- The same branch name is used in the backend and frontend repositories.
- Work is completed one sub-phase at a time.
- After a sub-phase is implemented and tested, development pauses for user
  validation.
- The sub-phase is committed only after user approval.
- Commit messages identify the completed sub-phase.
- After every complete phase, perform a broader review before beginning the
  next phase.
- Any new requirement or changed definition is added to this document under
  the affected phase before or alongside its implementation.
- Final merge and deployment happen only after all approved phases are
  complete.

Suggested commit format:

```text
Phase 1.1: Add monthly client metrics
```

## Metric Principles

- Store factual counts and amounts; derive percentages, rankings, and labels.
- Recalculate rates from their components instead of averaging percentages.
- Never add `SaleLine`, `ServicePurchase`, and `AttendanceVisit.revenue`
  together because they can represent overlapping revenue.
- Attendance belongs to `AttendanceVisit.visit_studio`.
- Service purchases belong to `ServicePurchase.studio`.
- General sales belong to `SaleLine.studio`.
- Site-wide client calculations group across studios without counting the same
  client-week more than once.
- Missing weekly rows represent zero activity.
- A client is attended when both `no_show=False` and `late_cancel=False`.
- New clients are evaluated only across eligible weeks beginning with their
  first visit or membership activation.
- Every score, segment, or health label must expose its calculation rule.

## Phase 1: Data Foundation

### Phase 1.1: Monthly Client Metrics

Status: Complete

Create `ClientStudioMonthlyMetric`, uniquely identified by:

```text
client + site + studio + month
```

Store factual monthly values:

- Attended visits
- Total bookings
- No-shows
- Late cancellations
- Active weeks
- Attendance revenue
- Service purchase count
- Service spending
- Membership spending
- Non-membership spending
- General sales spending
- First and last visit in the month
- First and last purchase in the month
- Active membership days
- Membership status

Internal support fields:

- `active_week_starts` stores the distinct Monday dates behind
  `active_weeks`.
- `active_membership_dates` stores the distinct covered dates behind
  `active_membership_days`.

These support fields allow site-level aggregation to union activity across
studios. For example, attendance at two studios in the same week counts as one
active week for the site, while the visits themselves still count separately.

This table supports selected-month, annual, multi-month, and lifetime
aggregations.

Implemented definitions:

- A monthly row is created when the client has attendance, service purchases,
  general sales, tracked membership coverage, or a retention status attributed
  to the studio during that month.
- Historical records without a studio are preserved in one unassigned
  client/site/month row instead of being discarded or guessed.
- `total_bookings` counts all attendance rows.
- `attended_visits` requires both `no_show=False` and `late_cancel=False`.
- `active_weeks` counts distinct Monday-based calendar weeks containing an
  attended visit.
- `attendance_revenue` sums attendance revenue independently from purchase
  revenue.
- `service_spending` includes all Sales by Service purchases sold during the
  month.
- `membership_spending` includes purchases whose pricing option has
  `track_retention=True`.
- `non_membership_spending` includes non-tracked, non-trial service purchases.
- Trial purchases remain in service spending and purchase count but are
  excluded from non-membership spending.
- `general_sales_spending` sums `SaleLine.paid_total` independently.
- First and last purchase dates consider both service purchases and general
  sales occurring during the month.
- Active membership days are the union of calendar dates covered by tracked
  purchases, so overlapping purchases cannot inflate the count.
- The rebuild atomically replaces all calculated rows for one site and month,
  making corrections and repeated rebuilds idempotent.

Validation:

- [x] Model and migration created
- [x] Rebuild service implemented
- [x] Cross-studio site totals avoid client duplication
- [x] Financial sources remain separate
- [x] Tests pass
- [x] User reviewed
- [x] Committed

### Phase 1.2: Weekly Client Metrics

Status: Not started

Create `ClientStudioWeeklyMetric`, uniquely identified by:

```text
client + site + studio + week_start
```

Store:

- Attended visits
- Total bookings
- No-shows
- Late cancellations
- Attendance revenue
- Active membership days
- Active membership indicator

Rows are created when a client has attendance, cancellation, purchase, or
active membership activity. Empty calendar weeks are interpreted as zero
without creating permanent rows.

Validation:

- [ ] Model and migration created
- [ ] Rebuild service implemented
- [ ] Week boundaries are consistent
- [ ] Missing weeks behave as zero
- [ ] Multi-studio attendance counts once at site-week scope
- [ ] Tests pass
- [ ] User reviewed
- [ ] Committed

### Phase 1.3: Automatic Rebuilding

Status: Not started

- Attendance imports rebuild affected weekly and monthly attendance metrics.
- Sales imports rebuild affected monthly general-sales metrics.
- Sales by Service imports rebuild affected purchase and membership metrics.
- Retention rebuilds update monthly membership status.
- Corrected reports recalculate existing rows instead of accumulating values.
- Add a protected manual historical rebuild action for initialization and
  repairs.

Validation:

- [ ] Each importer triggers only relevant rebuilds
- [ ] Corrected imports replace derived facts correctly
- [ ] Historical rebuild is idempotent
- [ ] Manual action is permission protected
- [ ] Tests pass
- [ ] User reviewed
- [ ] Committed

### Phase 1.4: Foundation Review

Status: Not started

Review metric definitions, performance, report overlap, site/studio attribution,
and historical rebuild behavior before beginning frontend development.

- [ ] Full Phase 1 test suite passes
- [ ] Historical data can be rebuilt
- [ ] Calculations checked against representative clients
- [ ] Phase review completed
- [ ] Changes or corrections documented

## Phase 2: Client Directory And Profile

### Phase 2.1: Client Directory

Status: Not started

Create a dedicated analytics page with:

- Search by name, Mindbody ID, email, and phone
- Site and studio selectors
- Month and predefined period selectors
- Membership-status filters
- Sorting and server-side pagination

Initial columns:

- Client
- Current membership status
- Primary studio
- Last visit and days since last visit
- Visits in the selected period
- Active weeks
- Attendance, no-show, and late-cancel rates
- Service spending
- Total sales spending

### Phase 2.2: Individual Client Overview

Status: Not started

Create an individual profile supporting:

- All-studio, site, and studio scopes
- Lifetime and selected-period summaries
- Current membership
- First and last visits
- First and last purchases
- Attendance and cancellation metrics
- Active weeks and membership months
- Service and total-sales spending

### Phase 2.3: Client Histories

Status: Not started

Add paginated histories for:

- Attendance
- Service purchases
- General sales
- Membership and retention
- Combined chronological timeline

### Phase 2.4: Basic Rankings

Status: Not started

Rank clients by site or studio for:

- Most attended
- Highest service spending
- Highest total-sales spending
- Most active weeks
- Best attendance rate
- Highest no-show rate
- Most recently active

Supported scopes:

- Selected month
- Last 3, 6, and 12 months
- Lifetime

### Phase 2.5: Directory And Profile Review

Status: Not started

- [ ] Metrics match raw records for representative clients
- [ ] Rankings match profile values
- [ ] Site and studio scopes behave correctly
- [ ] Pagination and permissions reviewed
- [ ] Phase review completed

## Phase 3: Regularity And Engagement

### Phase 3.1: Weekly Regularity

Status: Not started

Calculate:

- Active weeks in the last 4, 8, 12, 16, 26, and 52 weeks
- Eligible weeks
- Regularity percentage
- Average visits per active week
- Weeks with multiple visits
- Lifetime active weeks

```text
regularity = eligible weeks with attendance / total eligible weeks
```

### Phase 3.2: Attendance Streaks

Status: Not started

Calculate:

- Current weekly attendance streak
- Longest historical attendance streak
- Consecutive inactive weeks
- Active membership weeks without attendance

### Phase 3.3: Engagement Trends

Status: Not started

Compare recent and preceding periods and classify clients as:

- Increasing
- Stable
- Declining
- Inactive

### Phase 3.4: Preferences

Status: Not started

Calculate:

- Visits by instructor
- Favorite instructor and staff affinity
- Primary studio and cross-studio attendance
- Preferred weekdays and hours
- Most-used services and pricing options
- Group/private attendance where classification is reliable

### Phase 3.5: Regularity And Engagement Review

Status: Not started

- [ ] New-client eligible-week behavior reviewed
- [ ] Missing-week behavior reviewed
- [ ] Current and longest streaks validated
- [ ] Multi-studio regularity validated
- [ ] Phase review completed

## Phase 4: Retention And Client Value

### Phase 4.1: Membership History

Status: Not started

Calculate membership months, consecutive months, renewals, reactivations,
not-renewed events, interruptions, renewal delay, and longest membership gap.

### Phase 4.2: Financial Value

Status: Not started

Calculate separately:

- Lifetime total sales
- Lifetime service spending
- Membership and non-membership spending
- Selected-period spending
- Average purchase value
- Average spending per active month
- Average spending per tenure month
- Days since last purchase

### Phase 4.3: Loyalty Dimensions

Status: Not started

Represent loyalty using separate explainable dimensions:

- Tenure
- Attendance volume
- Weekly consistency
- Membership continuity
- Recency
- Attendance reliability
- Financial value

### Phase 4.4: Advanced Rankings

Status: Not started

Add rankings for most loyal, longest-tenured, most regular, most consistent,
most valuable, cross-studio, and newly engaged clients.

### Phase 4.5: Retention And Value Review

Status: Not started

- [ ] Financial totals validated without overlap
- [ ] Membership transitions validated
- [ ] Loyalty dimensions remain explainable
- [ ] Rankings checked against profiles
- [ ] Phase review completed

## Phase 5: Risk And Reactivation

### Phase 5.1: Transparent Health Labels

Status: Not started

Add documented labels such as:

- New client
- Active and consistent
- Declining attendance
- Recently inactive
- Frequent no-shows
- Frequent late cancellations
- Membership expired
- Attending after expiration
- Reactivated
- High-value at risk

### Phase 5.2: Not-Renewed Analysis

Status: Not started

Analyze not-renewed clients using lifetime visits, lifetime active weeks,
historical regularity, streaks, tenure, spending, recent attendance, expiration,
and post-expiration activity.

### Phase 5.3: Reactivation Rankings

Status: Not started

Provide two distinct views:

- Relationship value: historically important clients.
- Reactivation opportunity: clients most actionable now.

### Phase 5.4: Optional Health Score

Status: Not started

Consider a configurable health score only after the individual dimensions and
labels have been validated. The score may combine recency, engagement,
reliability, retention, and financial value.

### Phase 5.5: Final Module Review

Status: Not started

- [ ] Health rules are visible and understandable
- [ ] Reactivation rankings are operationally useful
- [ ] Permissions and financial visibility are correct
- [ ] Performance reviewed with production-scale data
- [ ] Documentation reflects final behavior
- [ ] Backend and frontend branches ready to merge

## Change Log

### 2026-06-13

- Created the Client Module V1 development plan.
- Established the phased validation and commit workflow.
- Selected monthly and weekly client-studio metrics as the calculation
  foundation.
- Implemented Phase 1.1 monthly client-studio metrics and their atomic rebuild
  service.
- Added internal active-week and membership-date support fields to prevent
  cross-studio duplication in site-level calculations.
- Defined non-membership spending as non-tracked and non-trial service
  purchases.
- User reviewed and approved Phase 1.1 for commit.
