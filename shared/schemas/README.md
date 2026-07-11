# Shared Schemas

This directory houses contracts and type definitions shared between the backend (Python/Pydantic) and frontend (TypeScript) layers.

## Purpose

- **Canonical Data Schema** objects that both the `DataSourceAdapter` layer (backend) and the frontend consume.
- **Response contracts** defining the shape of API responses.

## Convention

- Python schemas live in `backend/schemas/` and are the source of truth.
- TypeScript mirrors are generated or manually maintained here for frontend consumption.
