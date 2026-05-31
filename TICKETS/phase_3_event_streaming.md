# Phase 3: Event Schema & Streaming

## Goal
Define the exact event schema and implement the mechanism to stream/batch these events from the detection layer to the API.

## Tasks
- [ ] Define Pydantic models for the exact mandated event schema.
- [ ] Ensure event types include all 8 required events.
- [ ] Configure the event stream/batching from detection pipeline (can be direct API calls or via a bus like Kafka/Redis queue if decoupled).
- [ ] Support correlation of generated events with POS transactions (`pos_transactions.csv`) for billing queue abandonment logic.

## Documentation
- [ ] Document event schema design rationale in `CHOICES.md`.
