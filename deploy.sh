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
ENV_VARS_FILE=""
ENV_KEYS=()
ENV_VALUES=()

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

find_env_index() {
  local key="$1"
  for i in "${!ENV_KEYS[@]}"; do
    if [[ "${ENV_KEYS[$i]}" == "${key}" ]]; then
      printf '%s' "${i}"
      return 0
    fi
  done
  return 1
}

set_env_var() {
  local key="$1"
  local value="$2"
  local override="${3:-true}"
  local idx

  if idx="$(find_env_index "${key}")"; then
    if [[ "${override}" == "true" ]]; then
      ENV_VALUES[$idx]="${value}"
    fi
    return 0
  fi

  ENV_KEYS+=("${key}")
  ENV_VALUES+=("${value}")
}

parse_env_vars_string() {
  local input="$1"
  local buf=""
  local esc=0
  local -a parts=()

  for ((i=0; i<${#input}; i++)); do
    local ch="${input:i:1}"
    if ((esc)); then
      buf+="${ch}"
      esc=0
      continue
    fi
    if [[ "${ch}" == "\\" ]]; then
      esc=1
      continue
    fi
    if [[ "${ch}" == "," ]]; then
      parts+=("${buf}")
      buf=""
      continue
    fi
    buf+="${ch}"
  done
  parts+=("${buf}")

  for pair in "${parts[@]}"; do
    local key="${pair%%=*}"
    local value="${pair#*=}"
    key="$(trim "${key}")"
    value="$(trim "${value}")"
    [[ -z "${key}" || "${key}" == "${value}" ]] && continue

    value="${value//\\,/,}"

    if [[ "${key}" == "PORT" ]]; then
      continue
    fi
    if [[ "${key}" == "CLOUDSQL_INSTANCE" ]]; then
      if [[ -z "${CLOUDSQL_INSTANCE}" ]]; then
        CLOUDSQL_INSTANCE="${value}"
      fi
      continue
    fi

    set_env_var "${key}" "${value}" "true"
  done
}

load_env_file() {
  local file_path="$1"

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

    if [[ ( "${value}" == \"*\" && "${value}" == *\" ) || ( "${value}" == \'*\' && "${value}" == *\' ) ]]; then
      value="${value:1:-1}"
    fi

    set_env_var "${key}" "${value}" "false"
  done < "${file_path}"
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

if [[ -n "${ENV_VARS}" ]]; then
  parse_env_vars_string "${ENV_VARS}"
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

if [[ "${#ENV_KEYS[@]}" -gt 0 ]]; then
  ENV_VARS_FILE="$(mktemp -t env-vars-XXXX.yaml)"
  for i in "${!ENV_KEYS[@]}"; do
    key="${ENV_KEYS[$i]}"
    value="${ENV_VALUES[$i]}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s: "%s"\n' "${key}" "${value}" >> "${ENV_VARS_FILE}"
  done
  DEPLOY_ARGS+=("--env-vars-file" "${ENV_VARS_FILE}")
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

if [[ -n "${ENV_VARS_FILE}" ]]; then
  trap 'rm -f "${ENV_VARS_FILE}"' EXIT
fi

gcloud run deploy "${DEPLOY_ARGS[@]}"

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --platform managed --region "${REGION}" --format "value(status.url)")"
echo "Service URL: ${SERVICE_URL}"
echo "Deploy complete."
