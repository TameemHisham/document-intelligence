# Email alerts at 50/90/100% of the GCP budget (alerts only - GCP budgets don't stop spending;
# the in-app MONTHLY_BUDGET_USD cap and Cloud Run max instances are the hard limits).
resource "google_billing_budget" "monthly" {
  count           = var.billing_account == "" ? 0 : 1
  billing_account = var.billing_account
  display_name    = "document-intelligence"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }
  amount {
    # currency_code omitted: must match the billing account's currency (e.g. GBP), so let it default
    specified_amount {
      units = tostring(var.gcp_budget_usd)
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }
  depends_on = [google_project_service.apis]
}
