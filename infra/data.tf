resource "google_storage_bucket" "files" {
  name                        = "${var.project_id}-di-files"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning { enabled = false }
  depends_on = [google_project_service.apis]
}

resource "google_sql_database_instance" "db" {
  name                = "di-postgres"
  database_version    = "POSTGRES_16" # pgvector available via CREATE EXTENSION vector
  region              = var.region
  deletion_protection = true

  settings {
    tier              = var.db_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_size         = 10
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled = true # reachable only through the Cloud SQL connector (no authorized networks)
      ssl_mode     = "ENCRYPTED_ONLY"
    }
    backup_configuration {
      enabled = true
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "app" {
  name     = "di"
  instance = google_sql_database_instance.db.name
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.db.name
  password = random_password.db.result
}

# --- Secrets (values never live in env files or images)
resource "google_secret_manager_secret" "db_url" {
  secret_id = "di-database-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "db_url" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = "postgresql+psycopg://app:${random_password.db.result}@/di?host=/cloudsql/${google_sql_database_instance.db.connection_name}"
}

resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret" "jwt" {
  secret_id = "di-jwt-secret"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "jwt" {
  secret      = google_secret_manager_secret.jwt.id
  secret_data = random_password.jwt.result
}

# The Anthropic key is added by hand so it never enters Terraform state:
#   printf %s "$KEY" | gcloud secrets versions add di-anthropic-api-key --data-file=-
resource "google_secret_manager_secret" "anthropic" {
  secret_id = "di-anthropic-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "anthropic_placeholder" {
  secret      = google_secret_manager_secret.anthropic.id
  secret_data = "REPLACE_ME" # the app treats this as "no key" until a real version is added
  lifecycle {
    ignore_changes = [secret_data, enabled]
  }
}
