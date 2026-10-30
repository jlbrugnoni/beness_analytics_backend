# Cross-period occupancy dashboard

The Occupancy card lives in the dashboard's Cross-Period section. Its weekly/monthly
tabs above the filter bar preserve weekly reporting and adds calendar-month navigation and selection.
Site, studio, selected period and month persist in the URL and browser storage.

Monthly reporting includes capacity used, daily capacity/attendance bars, room totals,
and the ten lowest/highest occupancy slots across the complete month. The capacity
trend compares the selected month with five previous calendar months. Its tabs show
capacity usage, occupancy rate and available scheduled-class counts.

The hour matrix includes every operating date in the selected month. Its weekday
view filters to occurrences of the selected weekday within that month. Row, column
and overall totals divide summed matched attendance by summed available capacity;
they do not average percentages. Day labels and row totals stay pinned while the
hour columns scroll; the header stays visible while scrolling through the month.
As with the existing matrix, classes starting
within the same clock hour are grouped together. Blank cells mean no available class.

The monthly comparison plots daily occupancy against the previous calendar month,
aligned by day number, with dots connected across days without scheduled capacity.
Days with no capacity in either month are omitted; missing values are never shown
as zero occupancy. The capacity bar chart retains every calendar day in the month.
Current months show scheduled capacity for the full month, including future classes.

`GET /api/data/analytics/dashboard/occupancy/` accepts `mode=weekly|monthly`,
`date_from`, `date_to`, and the existing site/studio filters. Optional
`detail=trends|matrix` serves dialog data. Monthly periods normalize to the full
calendar month containing date_from. Authentication and existing location scoping
apply. No migrations or metric rebuilds are needed.

The endpoint reuses occupation_payload's available-class rules, excluding cancelled,
unavailable and closed classes. Its slot lists have no legacy 100-row truncation,
so end-of-month slots participate in rankings and matrix totals. Existing consumers
retain their default limit. Weekly drilldown dialogs retain their existing endpoints.

Validation: analytics.test_occupancy covers full-month slot completeness, closure
consistency, month/year transitions, comparison periods, studio filtering, attendance
aggregation, weekly ranges, invalid ranges and authentication.
