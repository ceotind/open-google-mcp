# GAQL quick tips

Rules that break Google Ads queries.

1. **Fully qualify every field.** `campaign.id`, not `id`. `metrics.clicks`, not `clicks`.
2. **Dates use dashes.** `2026-01-01`, never `2026/01/01`.
3. **Relative ranges use keywords.** `DURING LAST_7_DAYS`, `LAST_30_DAYS`, `THIS_MONTH`, `THIS_QUARTER`.
4. **Conditions are AND-combined.** There is no OR clause.
5. **Ordering is a string.** `metrics.clicks DESC`.
6. **`change_event` caps at 10,000 rows.** Other resources vary.
7. **Discover fields first.** Call `get_resource_metadata` before guessing a name.

Common conditions:

```
campaign.status = 'ENABLED'
campaign.advertising_channel_type = 'SEARCH'
segments.date DURING LAST_30_DAYS
metrics.impressions > 1000
```
