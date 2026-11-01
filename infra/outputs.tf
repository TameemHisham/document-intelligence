output "api_url" { value = google_cloud_run_v2_service.api.uri }
output "web_url" { value = google_cloud_run_v2_service.web.uri }
output "image_repo" { value = local.image_repo }

# Put these two in the GitHub repo's Actions variables (not secrets - they aren't sensitive).
output "gcp_wif_provider" { value = google_iam_workload_identity_pool_provider.github.name }
output "gcp_deployer_sa" { value = google_service_account.deployer.email }
