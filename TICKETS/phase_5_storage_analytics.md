# Phase 5: Storage, Analytics & POS Correlation

## Goal
Persist events, compute metrics, and correlate POS transactions to compute the North Star metric (Conversion Rate).

## Tasks
- [ ] Set up database (e.g., PostgreSQL/TimescaleDB/SQLite) for event storage.
- [ ] Implement POS correlation logic: Correlate `pos_transactions.csv` with visitor sessions by time window + store. (A visitor in the billing zone within the 5-minute window before a transaction timestamp counts as converted).
- [ ] Compute real-time metrics: unique visitors, conversion rate, average dwell per zone, queue depth, abandonment rate.
- [ ] Compute conversion funnel logic: Entry -> Zone Visit -> Billing Queue -> Purchase.

## Testing Requirements
- [ ] Add `# PROMPT:` and `# CHANGES MADE:` blocks at the top of all test files.
