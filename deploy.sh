#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-lineoa-g49}"
REGION="${REGION:-asia-southeast1}"
SERVICE_NAME_RAW="${SERVICE_NAME:-Backend_B}"
SERVICE_NAME="$(printf '%s' "${SERVICE_NAME_RAW}" | tr '[:upper:]' '[:lower:]' | tr '_' '-' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//')"
REPO_NAME="${REPO_NAME:-backend-repo}"
ALLOW_UNAUTHENTICATED="${ALLOW_UNAUTHENTICATED:-true}"
ENV_VARS="${ENV_VARS:-}"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT:-}"
ENV_FILE="${ENV_FILE:-}"
SECRET_VARS="${SECRET_VARS:-}"
SECRET_FILE="${SECRET_FILE:-.env.secrets}"
CLOUDSQL_INSTANCE="${CLOUDSQL_INSTANCE:-}"

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

load_env_file() {
  local file_path="$1"
  local -a env_pairs=()
  local existing_keys="|"

  if [[ -n "${ENV_VARS}" ]]; then
    IFS=',' read -r -a env_pairs <<< "${ENV_VARS}"
    for pair in "${env_pairs[@]}"; do
      local key="${pair%%=*}"
      key="$(trim "${key}")"
      if [[ -n "${key}" ]]; then
        existing_keys="${existing_keys}${key}|"
      fi
    done
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="$(trim "${line}")"
    [[ -z "${line}" || "${line:0:1}" == "#" ]] && continue
    line="${line#export }"

    local key="${line%%=*}"
    local value="${line#*=}"
    key="$(trim "${key}")"
    value="$(trim "${value}")"
    [[ -z "${key}" || "${key}" == "${value}" ]] && continue
    if [[ "${key}" == "PORT" ]]; then
      continue
    fi

    if [[ "${key}" == "CLOUDSQL_INSTANCE" ]]; then
      if [[ -z "${CLOUDSQL_INSTANCE}" ]]; then
        CLOUDSQL_INSTANCE="${value}"
      fi
      continue
    fi

    if [[ "${existing_keys}" == *"|${key}|"* ]]; then
      continue
    fi

    if [[ ( "${value}" == \"*\" && "${value}" == *\" ) || ( "${value}" == \'*\' && "${value}" == *\' ) ]]; then
      value="${value:1:-1}"
    fi

    env_pairs+=("${key}=${value}")
    existing_keys="${existing_keys}${key}|"
  done < "${file_path}"

  ENV_VARS="$(IFS=','; echo "${env_pairs[*]}")"
}

load_secret_file() {
  local file_path="$1"
  local -a secret_pairs=()
  local existing_keys="|"

  if [[ -n "${SECRET_VARS}" ]]; then
    IFS=',' read -r -a secret_pairs <<< "${SECRET_VARS}"
    for pair in "${secret_pairs[@]}"; do
      local key="${pair%%=*}"
      key="$(trim "${key}")"
      if [[ -n "${key}" ]]; then
        existing_keys="${existing_keys}${key}|"
      fi
    done
  fi

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="$(trim "${line}")"
    [[ -z "${line}" || "${line:0:1}" == "#" ]] && continue
    line="${line#export }"

    local key="${line%%=*}"
    local value="${line#*=}"
    key="$(trim "${key}")"
    value="$(trim "${value}")"
    [[ -z "${key}" || "${key}" == "${value}" ]] && continue

    if [[ "${existing_keys}" == *"|${key}|"* ]]; then
      continue
    fi

    if [[ ( "${value}" == \"*\" && "${value}" == *\" ) || ( "${value}" == \'*\' && "${value}" == *\' ) ]]; then
      value="${value:1:-1}"
    fi

    secret_pairs+=("${key}=${value}")
    existing_keys="${existing_keys}${key}|"
  done < "${file_path}"

  SECRET_VARS="$(IFS=','; echo "${secret_pairs[*]}")"
}

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud ไม่พบใน PATH"
  exit 1
fi

if [[ -z "${ENV_FILE}" ]]; then
  if [[ -f ".env.cloudrun" ]]; then
    ENV_FILE=".env.cloudrun"
  else
    ENV_FILE=".env"
  fi
fi

if [[ -f "${ENV_FILE}" ]]; then
  echo "Loading env from ${ENV_FILE}..."
  load_env_file "${ENV_FILE}"
fi

if [[ -f "${SECRET_FILE}" ]]; then
  echo "Loading secrets from ${SECRET_FILE}..."
  load_secret_file "${SECRET_FILE}"
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

if [[ -n "${SECRET_VARS}" ]]; then
  DEPLOY_ARGS+=("--set-secrets" "${SECRET_VARS}")
fi

if [[ -n "${SERVICE_ACCOUNT}" ]]; then
  DEPLOY_ARGS+=("--service-account" "${SERVICE_ACCOUNT}")
fi

if [[ -n "${CLOUDSQL_INSTANCE}" ]]; then
  DEPLOY_ARGS+=("--add-cloudsql-instances" "${CLOUDSQL_INSTANCE}")
fi

gcloud run deploy "${DEPLOY_ARGS[@]}"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format "value(status.url)")"
echo "Service URL: ${SERVICE_URL}"
echo "Deploy complete."
