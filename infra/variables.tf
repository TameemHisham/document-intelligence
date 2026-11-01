variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "github_repo" {
  description = "owner/name of the GitHub repo allowed to deploy via Workload Identity Federation"
  type        = string
}

variable "google_client_id" {
  description = "OAuth client ID for Google sign-in (public value)"
  type        = string
}

variable "db_tier" {
  description = "Cloud SQL tier. db-f1-micro is the cheapest (~$9/month, always on)."
  type        = string
  default     = "db-f1-micro"
}

variable "claude_model" {
  type    = string
  default = "claude-sonnet-5-5"
}

variable "gemini_model" {
  type    = string
  default = "gemini-2.5-flash-lite"
}

variable "app_monthly_budget_usd" {
  description = "In-app hard cap on Claude + Gemini + Vision spend"
  type        = number
  default     = 5
}

variable "billing_account" {
  description = "Billing account ID for a GCP budget alert (leave empty to skip)"
  type        = string
  default     = ""
}

variable "gcp_budget_usd" {
  description = "GCP billing budget for alert emails (infrastructure: Cloud SQL, Cloud Run, storage)"
  type        = number
  default     = 25
}

variable "max_instances" {
  description = "Upper bound per Cloud Run service - also a cost ceiling"
  type        = number
  default     = 3
}

variable "owner_emails" {
  description = "Comma-separated emails allowed to sign in with Google (full access); everyone else uses the guest demo"
  type        = string
}

variable "demo_enabled" {
  description = "Offer one-click guest sandboxes to visitors"
  type        = bool
  default     = true
}
