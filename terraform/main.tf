terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

# --- 1. VARIABLES ---
variable "project_id" {
  description = "Your Google Cloud Project ID"
  type        = string
}

variable "db_password" {
  description = "The database password"
  type        = string
  sensitive   = true # Hides it from logs
}

variable "region" {
  description = "Region for all resources"
  type        = string
  default     = "us-central1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  services = [
    "cloudresourcemanager.googleapis.com",
    "container.googleapis.com",
    "sqladmin.googleapis.com",
    "cloudfunctions.googleapis.com",
    "pubsub.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage-component.googleapis.com",
    "artifactregistry.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.services)

  project = var.project_id
  service = each.key

  disable_on_destroy = false
}

resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "google_storage_bucket" "raw_uploads" {
  name          = "raw-uploads-${var.project_id}-${random_id.bucket_suffix.hex}"
  location      = "US"
  force_destroy = true
}

resource "google_storage_bucket" "processed_images" {
  name          = "processed-${var.project_id}-${random_id.bucket_suffix.hex}"
  location      = "US"
  force_destroy = true
}

resource "google_storage_bucket" "func_bucket" {
  name          = "func-source-${var.project_id}-${random_id.bucket_suffix.hex}"
  location      = "US"
  force_destroy = true
}

# --- 3. DATABASE (CLOUD SQL) ---
resource "google_sql_database_instance" "postgres" {
  name             = "todo-db-${random_id.bucket_suffix.hex}"
  database_version = "POSTGRES_13"
  region           = var.region

  settings {
    tier = "db-f1-micro"
  }
  deletion_protection = false 
}

resource "google_sql_database" "database" {
  name     = "todo_app"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "users" {
  name     = "app_user"
  instance = google_sql_database_instance.postgres.name
  # Use the variable instead of "securepassword"
  password = var.db_password 
}

# --- 4. PUB/SUB ---
resource "google_pubsub_topic" "compression" {
  name = "compression-jobs"
}

resource "google_pubsub_subscription" "worker_sub" {
  name  = "compression-sub"
  topic = google_pubsub_topic.compression.name
}

# --- 5. CLOUD FUNCTION (SERVERLESS ENCODER) ---
data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../functions"
  output_path = "${path.module}/function.zip"
}

resource "google_storage_bucket_object" "archive" {
  name   = "source.zip"
  bucket = google_storage_bucket.func_bucket.name
  source = data.archive_file.function_zip.output_path
}

resource "google_storage_bucket_iam_member" "public_access" {
  bucket = google_storage_bucket.processed_images.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_cloudfunctions_function" "security_service" {
  name        = "crypto-func"
  description = "Encrypts text using substitution"
  runtime     = "python310"
  region      = var.region

  available_memory_mb   = 128
  source_archive_bucket = google_storage_bucket.func_bucket.name
  source_archive_object = google_storage_bucket_object.archive.name
  trigger_http          = true
  entry_point           = "crypto_handler" # Updated to match your new function name

  # Note: Environment variables removed as they are no longer needed
}

# Make Function Public for Demo
resource "google_cloudfunctions_function_iam_member" "invoker" {
  project        = google_cloudfunctions_function.security_service.project
  region         = google_cloudfunctions_function.security_service.region
  cloud_function = google_cloudfunctions_function.security_service.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# --- 6. GKE CLUSTER (UPDATED FIX) ---
resource "google_container_cluster" "primary" {
  name     = "todo-cluster"
  
  location = "${var.region}-a" 
  
  initial_node_count = 1

  node_config {
    machine_type = "e2-medium"
    
    disk_size_gb = 30
    disk_type    = "pd-standard"
    
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]
  }
}

# --- 7. DEPLOYMENT LOGIC ---
resource "null_resource" "docker_auth" {
  provisioner "local-exec" {
    command = "gcloud auth configure-docker"
  }
}

resource "null_resource" "docker_build_push" {
  depends_on = [null_resource.docker_auth, google_container_cluster.primary]

  triggers = {
    always_run = "${timestamp()}"
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
    command     = <<EOT
      echo "SUBMITTING BUILDS TO CLOUD BUILD..."
      
      # Build API
      gcloud builds submit \
        --tag gcr.io/${var.project_id}/todo-api:v1 \
        ./app
      
      # Build Worker
      gcloud builds submit \
        --tag gcr.io/${var.project_id}/todo-worker:v1 \
        ./worker
    EOT
  }
}

resource "null_resource" "k8s_deploy" {
  depends_on = [
    null_resource.docker_build_push, 
    google_container_cluster.primary,
    google_sql_database_instance.postgres,
    google_storage_bucket.raw_uploads,
    google_cloudfunctions_function.security_service
  ]

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
    command     = <<EOT
      echo "GETTING CREDENTIALS..."
      gcloud container clusters get-credentials ${google_container_cluster.primary.name} \ 
      --zone ${var.region}-a \
      --project ${var.project_id}

      echo "INJECTING VARIABLES & DEPLOYING..."
      
      # 1. Deploy API
      sed -e 's|YOUR_PROJECT_ID|${var.project_id}|g' \
          -e 's|YOUR_RAW_BUCKET_NAME|${google_storage_bucket.raw_uploads.name}|g' \
          -e 's|YOUR_CLOUD_FUNCTION_URL|${google_cloudfunctions_function.security_service.https_trigger_url}|g' \
          -e 's|YOUR_DB_CONNECTION_NAME|${google_sql_database_instance.postgres.connection_name}|g' \
          -e 's|YOUR_DB_PASSWORD|${var.db_password}|g' \
          k8s/api.yaml | kubectl apply -f -

      # 2. Deploy Worker
      sed -e 's|YOUR_PROJECT_ID|${var.project_id}|g' \
          -e 's|YOUR_RAW_BUCKET_NAME|${google_storage_bucket.raw_uploads.name}|g' \
          -e 's|YOUR_PUBLIC_BUCKET_NAME|${google_storage_bucket.processed_images.name}|g' \
          -e 's|YOUR_DB_CONNECTION_NAME|${google_sql_database_instance.postgres.connection_name}|g' \
          -e 's|YOUR_DB_PASSWORD|${var.db_password}|g' \
          k8s/worker.yaml | kubectl apply -f -

      # 3. Deploy HPAs
      kubectl apply -f k8s/hpa.yaml
    EOT
  }
}