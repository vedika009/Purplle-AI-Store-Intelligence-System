# Phase 4: Anomaly Detection

## Goal
Detect operational anomalies based on the incoming event stream.

## Tasks
- [ ] Implement detection for `queue spike` (queue depth > threshold).
- [ ] Implement detection for `conversion drop` vs 7-day average.
- [ ] Implement detection for `dead zone` (no visits in 30 min).
- [ ] Assign severity (`INFO`, `WARN`, `CRITICAL`) and generate a `suggested_action` string for each anomaly.

## Testing Requirements
- [ ] Add `# PROMPT:` and `# CHANGES MADE:` blocks at the top of all test files.
