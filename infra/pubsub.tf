resource "google_pubsub_topic" "ingest" {
  name       = "ingest"
  depends_on = [google_project_service.apis]
}

resource "google_pubsub_topic" "ingest_dead_letter" {
  name = "ingest-dead-letter"
}

resource "google_pubsub_subscription" "ingest_dead_letter" {
  name                       = "ingest-dead-letter"
  topic                      = google_pubsub_topic.ingest_dead_letter.id
  message_retention_duration = "604800s" # keep failed jobs 7 days for inspection
}

# Push to the worker; Cloud Run scales workers from zero with the queue.
resource "google_pubsub_subscription" "ingest_push" {
  name                 = "ingest-push"
  topic                = google_pubsub_topic.ingest.id
  ack_deadline_seconds = 600

  push_config {
    push_endpoint = "${local.worker_url}/pubsub/push"
    oidc_token {
      service_account_email = google_service_account.pubsub_push.email
      audience              = local.worker_url
    }
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.ingest_dead_letter.id
    max_delivery_attempts = 5
  }

  expiration_policy {
    ttl = "" # never expire
  }
}

# Pub/Sub's service agent must be able to move undeliverable messages to the dead-letter topic.
locals {
  pubsub_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  topic  = google_pubsub_topic.ingest_dead_letter.id
  role   = "roles/pubsub.publisher"
  member = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "dlq_subscriber" {
  subscription = google_pubsub_subscription.ingest_push.id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}
