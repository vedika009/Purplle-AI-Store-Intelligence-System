# Phase 2: Computer Vision Layer

## Goal
Process CCTV clips, detect/track people, assign session tokens, and produce a stream of structured behavioural events according to the exact schema.

## Tasks
- [x] Set up object detection (e.g., YOLOv8) and tracking (e.g., ByteTrack).
- [x] Implement Re-ID logic to assign a unique, per-session `visitor_id`.
- [x] Implement `is_staff` classification (e.g., using uniform color or tracking across multiple zones in short timeframes).
- [x] Implement zone mapping based on `store_layout.json`.
- [x] Implement event extraction for 8 specific types: `ENTRY`, `EXIT`, `ZONE_ENTER`, `ZONE_EXIT`, `ZONE_DWELL`, `BILLING_QUEUE_JOIN`, `BILLING_QUEUE_ABANDON`, `REENTRY`.
- [x] Handle specific edge cases: Group entry, staff movement exclusion, re-entry (must produce REENTRY), partial occlusion, billing queue buildup, empty store periods, and camera angle overlap (deduplication).
- [x] Emit events matching the exact mandated schema (including `event_id`, `visitor_id`, `is_staff`, `dwell_ms`, `metadata.queue_depth`, etc.).

## Testing Requirements
- [x] Add `# PROMPT:` and `# CHANGES MADE:` blocks at the top of all test files (Part D AI Engineering requirement).
- [x] Ensure tests cover specific clip edge cases (empty store, all-staff clip, zero purchases, re-entry in funnel).

## Documentation
- [x] Document model selection, `is_staff` strategy, and edge case handling in `CHOICES.md`.
