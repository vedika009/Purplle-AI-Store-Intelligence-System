# Phase 6: Production API

## Goal
Expose analytics via a robust API.

## Tasks
- [ ] Develop FastAPI endpoints:
  - `GET /stores/{id}/footfall`
  - `GET /stores/{id}/heatmap`
  - `GET /stores/{id}/queue`
  - `GET /stores/{id}/anomalies`
  - `WS /stores/{id}/live`
  - `POST /stores/{id}/zones`
- [ ] Implement Authentication (JWT/API Key).
- [ ] Add rate limiting (`slowapi`).
- [ ] Configure Swagger UI documentation.
- [ ] Define Pydantic models for request/response.
