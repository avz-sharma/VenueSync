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

## Production Deployment (Google Cloud Run)

VenueSync is deployed as a single, unified container running on Google Cloud Run. The React frontend is built as static assets and served directly by the FastAPI backend.

### Required Environment Variables
The following environment variables must be configured in Cloud Run (do **not** commit these to GitHub):
- `GEMINI_API_KEY`: Your Gemini API key.
- `DATA_SOURCE`: Either `synthetic` or `upload`.
- `LOG_LEVEL`: Configures structured logging (e.g., `INFO`).

*(Note: `VITE_API_URL` is not needed in production as everything runs on the same origin).*

### Deployment Pipeline
The application uses Google Cloud Build connected to GitHub. Pushing to the `main` branch triggers the deployment pipeline defined in `cloudbuild.yaml`.

#### Manual Setup Required:
To enable the pipeline, you must complete the following one-time setup in your Google Cloud Project:
1. **Connect Repository:** Connect your GitHub repository to a Cloud Build Trigger.
2. **Secret Manager:** Store your Gemini API key in Google Secret Manager as `gemini-api-key`.
3. **IAM Permissions:** Grant the Cloud Build service account the following roles:
   - *Cloud Run Admin*
   - *Service Account User*
   - *Secret Manager Secret Accessor* (to read the API key)

### Local Docker Testing
You can build and test the unified production container locally:
```bash
# Build the unified image
docker build -t venuesync .

# Run locally on port 5005
docker run -e PORT=5005 -p 5005:5005 venuesync
```
Access the application at `http://localhost:5005`.
