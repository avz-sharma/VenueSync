param (
    [Parameter(Mandatory=$true)]
    [string]$ProjectId,

    [Parameter(Mandatory=$true)]
    [string]$GithubUsername,

    [Parameter(Mandatory=$true)]
    [string]$RepoName,

    [Parameter(Mandatory=$true)]
    [string]$GeminiApiKey
)

Write-Host "========================================"
Write-Host "VenueSync - Google Cloud Deployment Setup"
Write-Host "========================================"
Write-Host ""

# Part 0.1
Write-Host "[0.1] Setting the active project..."
gcloud config set project $ProjectId
if ($LASTEXITCODE -ne 0) { throw "Failed to set project" }

# Part 0.2
Write-Host "[0.2] Enabling required APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
if ($LASTEXITCODE -ne 0) { throw "Failed to enable APIs" }

# Part 0.3
Write-Host "[0.3] Creating Artifact Registry repo..."
gcloud artifacts repositories create venuesync-repo --repository-format=docker --location=us-central1 --description="VenueSync container images"
# Ignore if it already exists

# Part 0.4
Write-Host "[0.4] Creating Gemini API key secret..."
# Create or update the secret
$secretExists = (gcloud secrets list --filter="name:GEMINI_API_KEY" --format="value(name)" 2>$null)
if ([string]::IsNullOrWhiteSpace($secretExists)) {
    Write-Host "Creating new secret..."
    Write-Output $GeminiApiKey | gcloud secrets create GEMINI_API_KEY --data-file=-
} else {
    Write-Host "Secret exists, adding new version..."
    Write-Output $GeminiApiKey | gcloud secrets versions add GEMINI_API_KEY --data-file=-
}

# Part 0.5
Write-Host "[0.5] Granting IAM roles..."
$ProjectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
if (-not $ProjectNumber) { throw "Failed to get Project Number" }

gcloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:${ProjectNumber}@cloudbuild.gserviceaccount.com" --role="roles/run.admin"
gcloud projects add-iam-policy-binding $ProjectId --member="serviceAccount:${ProjectNumber}@cloudbuild.gserviceaccount.com" --role="roles/iam.serviceAccountUser"
gcloud secrets add-iam-policy-binding GEMINI_API_KEY --member="serviceAccount:${ProjectNumber}-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"

# Part 0.6
Write-Host "[0.6] Ensure you have connected GitHub via the Console first."
Write-Host "Attempting to create Cloud Build trigger via CLI..."
gcloud builds triggers create github --repo-name=$RepoName --repo-owner=$GithubUsername --branch-pattern="^main$" --build-config="cloudbuild.yaml" --name="venuesync-deploy-on-push"
# May fail if not connected, but let script continue

# Part 1
Write-Host "[1.0] Running manual first deploy sanity check..."
$ImageTag = "us-central1-docker.pkg.dev/$ProjectId/venuesync-repo/venuesync:manual-test"

Write-Host "Building Docker image..."
docker build -t $ImageTag .
if ($LASTEXITCODE -ne 0) { throw "Docker build failed" }

Write-Host "Configuring Docker auth..."
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

Write-Host "Pushing Docker image..."
docker push $ImageTag
if ($LASTEXITCODE -ne 0) { throw "Docker push failed" }

Write-Host "Deploying to Cloud Run..."
gcloud run deploy venuesync `
  --image=$ImageTag `
  --region=us-central1 `
  --platform=managed `
  --allow-unauthenticated `
  --min-instances=0 `
  --max-instances=3 `
  --memory=512Mi `
  --cpu=1 `
  --set-secrets=GEMINI_API_KEY=GEMINI_API_KEY:latest `
  --set-env-vars=DATA_SOURCE=production,LOG_LEVEL=info

if ($LASTEXITCODE -ne 0) { throw "Cloud Run deployment failed" }

# Part 3
Write-Host "[3.0] Verifying deployment..."
$ServiceUrl = gcloud run services describe venuesync --region=us-central1 --format="value(status.url)"
if (-not $ServiceUrl) { throw "Failed to get service URL" }

Write-Host "Live URL: $ServiceUrl"
Write-Host "Testing SPA load (expect 200)..."
curl -I $ServiceUrl

Write-Host "Testing API health route..."
curl "$ServiceUrl/api/health"

Write-Host "Testing bogus API path (expect 404)..."
curl -I "$ServiceUrl/api/does-not-exist"

Write-Host ""
Write-Host "Setup complete. If all checks passed, your deployment is live!"
Write-Host "Ongoing deploys will be triggered automatically when you push to the 'main' branch."
