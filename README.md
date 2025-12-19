## 🚀 Prerequisites

Ensure you have the following installed:

- [Google Cloud SDK (gcloud)](https://cloud.google.com/sdk/docs/install)
- [Terraform](https://developer.hashicorp.com/terraform/downloads)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Python 3.9+](https://www.python.org/downloads/)
- [Locust](https://locust.io/) (for load testing)

## 🛠 Setup & Deployment

### 1. Configure Google Cloud

Login and set your project:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 2. Configure Terraform

Navigate to the `terraform` directory and create/update your variables:

1. Open `terraform/terraform.tfvars`.
2. Set your `project_id`.
3. (Optional) Change `region` or `db_password`.

```hcl
project_id  = "your-gcp-project-id"
region      = "us-central1"
db_password = "SuperSecretPassword123"
```

### NOTE

If you are using bash not powershell, you should run "sed -i 's/\r$//' main.tf" in terraform folder to change files from crlf to lf. 

### 3. Deploy Infrastructure

Initialize and apply the Terraform configuration. This will provision GKE, Cloud SQL, Buckets, etc., and deploy the application code.

```bash
cd terraform
terraform init
terraform apply
```


### 4. Verify Deployment

Get the external IP of your application:

```bash
kubectl get services
```

Look for `todo-api-service` and visit the `EXTERNAL-IP` in your browser.

## 🧪 Load Testing with Locust


   Update `locust_test.py` with your external IP if needed, or pass it via command line:

   ```bash
   # Run headless (no UI)
   locust -f locust_test.py --headless -u 10 -r 2 -t 5m -H http://YOUR_EXTERNAL_IP

   # Run with UI (open http://localhost:8089)
   locust -f locust_test.py -H http://YOUR_EXTERNAL_IP
   ```

   **Test Scenarios:**
   - **Read**: Simulates users viewing the homepage (`--tags read`).
   - **Write**: Simulates users creating text todos and uploading images (`--tags write`).

## 🧹 Cleanup

To remove all resources and avoid costs:

```bash
cd terraform
terraform destroy
```
