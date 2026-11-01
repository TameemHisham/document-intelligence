# One service account per workload, each with only what it needs.

resource "google_service_account" "api" {
  account_id   = "di-api"
  display_name = "Document Intelligence API"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "worker" {
  account_id   = "di-worker"
  display_name = "Document Intelligence ingest worker"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "web" {
  account_id   = "di-web"
  display_name = "Document Intelligence frontend (no permissions)"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "pubsub_push" {
  account_id   = "di-pubsub-push"
  display_name = "Pub/Sub push identity (invokes the worker)"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "deployer" {
  account_id   = "di-deployer"
  display_name = "GitHub Actions deployer (via Workload Identity Federation)"
  depends_on   = [google_project_service.apis]
}

# --- API: Cloud SQL, read/write its bucket, publish ingest jobs, call Gemini on Vertex, read its secrets
resource "google_project_iam_member" "api_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "api_bucket" {
  bucket = google_storage_bucket.files.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_pubsub_topic_iam_member" "api_publish" {
  topic  = google_pubsub_topic.ingest.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.api.email}"
}

# --- Worker: Cloud SQL, read files (Vision OCR needs only the enabled API), read its secrets
resource "google_project_iam_member" "worker_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_storage_bucket_iam_member" "worker_bucket" {
  bucket = google_storage_bucket.files.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.worker.email}"
}

# --- Secrets: access granted per secret, not project-wide
locals {
  secret_access = {
    api_db        = { secret = google_secret_manager_secret.db_url.id, sa = google_service_account.api.email }
    api_jwt       = { secret = google_secret_manager_secret.jwt.id, sa = google_service_account.api.email }
    api_anthropic = { secret = google_secret_manager_secret.anthropic.id, sa = google_service_account.api.email }
    wkr_db        = { secret = google_secret_manager_secret.db_url.id, sa = google_service_account.worker.email }
    wkr_anthropic = { secret = google_secret_manager_secret.anthropic.id, sa = google_service_account.worker.email }
  }
}

resource "google_secret_manager_secret_iam_member" "access" {
  for_each  = local.secret_access
  secret_id = each.value.secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.sa}"
}

# --- Pub/Sub push identity may invoke only the worker
resource "google_cloud_run_v2_service_iam_member" "push_invokes_worker" {
  name     = google_cloud_run_v2_service.worker.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_push.email}"
}

# Pub/Sub's service agent mints the OIDC token for push requests.
resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.pubsub_push.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# --- Public entry points (the API does its own auth)
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = { api = google_cloud_run_v2_service.api.name, web = google_cloud_run_v2_service.web.name }
  name     = each.value
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# --- GitHub Actions: keyless auth via Workload Identity Federation, limited to this repo's main branch
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repo}' && assertion.ref == 'refs/heads/main'"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# Deployer: push images to this one repo, and roll out new revisions of these three services only.
resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  repository = google_artifact_registry_repository.images.name
  location   = var.region
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_cloud_run_v2_service_iam_member" "deployer_run" {
  for_each = {
    api    = google_cloud_run_v2_service.api.name
    worker = google_cloud_run_v2_service.worker.name
    web    = google_cloud_run_v2_service.web.name
  }
  name     = each.value
  location = var.region
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

# A new revision runs as the service's identity, so the deployer must be allowed to "act as" it.
resource "google_service_account_iam_member" "deployer_act_as" {
  for_each = {
    api    = google_service_account.api.name
    worker = google_service_account.worker.name
    web    = google_service_account.web.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
