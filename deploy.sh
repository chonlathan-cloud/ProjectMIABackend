#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-lineoa-g49}"
REGION="${REGION:-asia-southeast1}"
SERVICE_NAME_RAW="${SERVICE_NAME:-Backend_B}"
SERVICE_NAME="$(printf '%s' "${SERVICE_NAME_RAW}" | tr '[:upper:]' '[:lower:]')"
REPO_NAME="${REPO_NAME:-backend-repo}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"
ENV_VARS="${ENV_VARS:-}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-}"

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud ไม่พบใน PATH"
  exit 1
fi

echo "Project: ${PROJECT_ID}"
echo "Region: ${REGION}"
if [[ "${SERVICE_NAME_RAW}" != "${SERVICE_NAME}" ]]; then
  echo "Service: ${SERVICE_NAME} (normalized from ${SERVICE_NAME_RAW})"
else
  echo "Service: ${SERVICE_NAME}"
fi
echo "Repo: ${REPO_NAME}"
echo "Image: ${IMAGE}"

gcloud config set project "${PROJECT_ID}" >/dev/null

echo "Enabling required services..."
gcloud services enable cloudbuild.googleapis.com run.googleapis.com artifactregistry.googleapis.com --project "${PROJECT_ID}" >/dev/null

echo "Checking Artifact Registry repo..."
if ! gcloud artifacts repositories describe "${REPO_NAME}" --project="${PROJECT_ID}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${REPO_NAME}" \
    --project="${PROJECT_ID}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Docker repository for ${SERVICE_NAME}"
fi

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")"
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "Ensuring Artifact Registry write access for build service accounts..."
for SA in "${CLOUDBUILD_SA}" "${COMPUTE_SA}"; do
  gcloud artifacts repositories add-iam-policy-binding "${REPO_NAME}" \
    --location "${REGION}" \
    --project "${PROJECT_ID}" \
    --member "serviceAccount:${SA}" \
    --role "roles/artifactregistry.writer" >/dev/null
done

gcloud builds submit --tag "${IMAGE}" .

DEPLOY_ARGS=(
  "${SERVICE_NAME}"
  "--image" "${IMAGE}"
  "--region" "${REGION}"
  "--platform" "managed"
  "--port" "8080"
)

if [[ "${ALLOW_UNAUTHENTICATED}" == "true" ]]; then
  DEPLOY_ARGS+=("--allow-unauthenticated")
fi

if [[ -n "${ENV_VARS}" ]]; then
  DEPLOY_ARGS+=("--set-env-vars" "${ENV_VARS}")
fi

if [[ -n "${SERVICE_ACCOUNT}" ]]; then
  DEPLOY_ARGS+=("--service-account" "${SERVICE_ACCOUNT}")
fi

gcloud run deploy "${DEPLOY_ARGS[@]}"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format "value(status.url)")"
echo "Service URL: ${SERVICE_URL}"
echo "Deploy complete."
