# VenueSync

**One-Line Pitch:** VenueSync ingests live zone-level crowd, staffing, and incident data, reasons over it against venue constraints, and hands the organizer a ranked, explained action queue.

## Architecture Overview

VenueSync relies on a strict, deterministic processing loop designed for crowd management and operational intelligence. The system strictly isolates raw data processing from the LLM reasoning engine, adhering to the following data flow:

1. **Input (Live Venue State):** Data is ingested from various sources, such as live camera feeds, gate sensor logs, and manual incident reports.
2. **Deterministic Pre-processing:** The system normalizes and cleans the data deterministically using Python preprocessors (e.g., occupancy rates, threshold-breach detection). This guarantees numerical accuracy and enforces a Canonical Data Schema.
3. **LLM Reasoning Engine:** Cleaned, structured data is passed to the LLM (Gemini 3.1 Pro) exclusively for high-level judgment and prioritization. The model outputs a validated JSON structure with prioritized actions and rationale.
4. **Output (Ranked Action Queue):** The finalized actions and explanations are sent to the frontend for operators to review and execute.

## Getting Started

### Toggling Data Sources

You can configure the application to use either synthetic, generated data or upload custom real-world CSV files. This is controlled by the `DATA_SOURCE` environment variable.

1. Open your `.env` file (or `.env.local` if running locally).
2. Set the `DATA_SOURCE` variable:
   - For **synthetic** data generation:
     ```env
     DATA_SOURCE=synthetic
     ```
   - For **file upload** processing:
     ```env
     DATA_SOURCE=upload
     ```
3. Restart the backend server to apply the changes.

### Running the Application

**Backend** (run from the project root):
```bash
uvicorn backend.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm run dev
```
