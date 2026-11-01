terraform {
  required_version = ">= 1.6"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  # Remote state (create the bucket once by hand, then uncomment):
  # backend "gcs" { bucket = "YOUR_PROJECT-tfstate", prefix = "document-intelligence" }
}

provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true # needed for the Billing Budgets API with user credentials
  billing_project       = var.project_id
}

data "google_project" "this" {}

locals {
  # Cloud Run URLs are deterministic, which lets services reference each other without cycles.
  url_suffix = "${data.google_project.this.number}.${var.region}.run.app"
  worker_url = "https://worker-${local.url_suffix}"
  web_url    = "https://web-${local.url_suffix}"
  image_repo = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "sqladmin.googleapis.com",
    "pubsub.googleapis.com",
    "secretmanager.googleapis.com",
    "vision.googleapis.com",
    "aiplatform.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com", # also enable by hand on a brand-new project (Terraform reads it first)
    "serviceusage.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "document-intelligence"
  format        = "DOCKER"
  location      = var.region
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions { keep_count = 10 }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition { older_than = "2592000s" } # 30 days
  }
  depends_on = [google_project_service.apis]
}
