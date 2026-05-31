# Phase 3: Event Streaming

## Goal
Establish a robust, scalable event backbone and stream processing.

## Tasks
- [ ] Configure Kafka (or Redpanda) as the event bus.
- [ ] Define event schema (JSON/Avro) for: `store.events.entry`, `store.events.dwell`, `store.events.queue`, `store.events.anomaly`.
- [ ] Implement stream processing (using Faust or Flink):
  - Tumbling windows (5-minute buckets) for footfall.
  - Session windows for dwell-time aggregation.
  - Sliding windows for rolling averages.

## Documentation
- [ ] Document justification for Kafka choice (Replay capability).
