# Images are rolled out by CI (`gcloud run deploy --image`); Terraform owns everything else.
locals {
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"

  common_env = {
    STORAGE_BACKEND    = "gcs"
    GCS_BUCKET         = google_storage_bucket.files.name
    VECTOR_BACKEND     = "pgvector"
    OCR_BACKEND        = "vision"
    GCP_PROJECT        = var.project_id
    GCP_LOCATION       = var.region
    CLAUDE_MODEL       = var.claude_model
    MONTHLY_BUDGET_USD = tostring(var.app_monthly_budget_usd)
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = "api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.api.email
    max_instance_request_concurrency = 20
    timeout                          = "120s"
    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [google_sql_database_instance.db.connection_name] }
    }
    containers {
      image = local.placeholder_image
      resources {
        limits            = { cpu = "2", memory = "4Gi" } # SBERT + CLIP for query embeddings
        cpu_idle          = true
        startup_cpu_boost = true
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      dynamic "env" {
        for_each = merge(local.common_env, {
          TASK_BACKEND      = "pubsub"
          PUBSUB_TOPIC      = google_pubsub_topic.ingest.name
          GEMINI_USE_VERTEX = "true"
          GEMINI_MODEL      = var.gemini_model
          GOOGLE_CLIENT_ID  = var.google_client_id
          FRONTEND_ORIGIN   = local.web_url
          DEV_AUTH          = "false"
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = {
          DATABASE_URL      = google_secret_manager_secret.db_url.secret_id
          JWT_SECRET        = google_secret_manager_secret.jwt.secret_id
          ANTHROPIC_API_KEY = google_secret_manager_secret.anthropic.secret_id
        }
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.access, google_secret_manager_secret_version.anthropic_placeholder]
}

resource "google_cloud_run_v2_service" "worker" {
  name                = "worker"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY" # only Pub/Sub push reaches it
  deletion_protection = false

  template {
    service_account                  = google_service_account.worker.email
    max_instance_request_concurrency = 1 # one image at a time; scale out instead
    timeout                          = "600s"
    scaling {
      min_instance_count = 0 # scale to zero when the queue is empty
      max_instance_count = var.max_instances
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [google_sql_database_instance.db.connection_name] }
    }
    containers {
      image   = local.placeholder_image
      command = ["sh", "-c", "exec uvicorn app.worker:app --host 0.0.0.0 --port $PORT"]
      resources {
        limits            = { cpu = "2", memory = "4Gi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      dynamic "env" {
        for_each = merge(local.common_env, {
          PUBSUB_PUSH_AUDIENCE = local.worker_url
          PUBSUB_PUSH_SA_EMAIL = google_service_account.pubsub_push.email
        })
        content {
          name  = env.key
          value = env.value
        }
      }
      dynamic "env" {
        for_each = {
          DATABASE_URL      = google_secret_manager_secret.db_url.secret_id
          ANTHROPIC_API_KEY = google_secret_manager_secret.anthropic.secret_id
        }
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, template[0].containers[0].command, client, client_version]
  }
  depends_on = [google_secret_manager_secret_iam_member.access, google_secret_manager_secret_version.anthropic_placeholder]
}

resource "google_cloud_run_v2_service" "web" {
  name                = "web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.web.email
    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }
    containers {
      image = local.placeholder_image
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
  depends_on = [google_project_service.apis]
}
