# Deployment Guide

This document outlines the steps required to set up a complete CI/CD pipeline for this trading system backend using Google Cloud Build. The pipeline is defined in the `cloudbuild.yaml` file at the root of this repository.

## Overview

The CI/CD pipeline automates the deployment of the four initial services:
- **Cloud Run Services:** `alpha-model-py`, `risk-model-py`
- **Cloud Functions:** `data_ingestion_py`, `tcost_model_py`

When triggered (e.g., by a push to your `main` branch), Cloud Build will execute the steps in `cloudbuild.yaml` to build, push, and deploy each service to your Google Cloud project.

## 1. Prerequisites (One-Time Setup)

Before creating the Cloud Build trigger, you must perform the following setup steps in your Google Cloud project.

### a. Enable APIs

Ensure the following APIs are enabled for your project. You can do this via the Cloud Console UI or using the `gcloud` CLI.

```bash
# Replace $PROJECT_ID with your actual GCP Project ID
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable iam.googleapis.com
```

### b. Grant IAM Permissions to Cloud Build

The Cloud Build service account needs permission to deploy services, manage artifacts, and act as a service account user.

1.  Find your Cloud Build service account email address. It will look like `[PROJECT_NUMBER]@cloudbuild.gserviceaccount.com`. You can find this in the IAM section of the Cloud Console.
2.  Grant the following roles to this service account:
    - **Cloud Run Admin (`roles/run.admin`):** To deploy and manage Cloud Run services.
    - **Cloud Functions Developer (`roles/cloudfunctions.developer`):** To deploy and manage Cloud Functions.
    - **Service Account User (`roles/iam.serviceAccountUser`):** To allow Cloud Run/Functions to run as the Compute Engine default service account.
    - **Artifact Registry Writer (`roles/artifactregistry.writer`):** To push Docker images to Artifact Registry.

You can grant these roles via the Cloud Console UI or with the following `gcloud` commands:

```bash
# Replace $PROJECT_NUMBER with your project number
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${CLOUDBUILD_SA}" --role="roles/run.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${CLOUDBUILD_SA}" --role="roles/cloudfunctions.developer"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${CLOUDBUILD_SA}" --role="roles/iam.serviceAccountUser"
gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:${CLOUDBUILD_SA}" --role="roles/artifactregistry.writer"
```

### c. Create Artifact Registry Repository

The pipeline needs a place to store the Docker images for the Cloud Run services.

1.  Create a Docker repository in Artifact Registry. The `cloudbuild.yaml` file assumes the repository name is `trading-system-repo` and it is located in the region specified by `_GCP_REGION`.

```bash
# Replace with your desired region
export GCP_REGION="us-central1"

gcloud artifacts repositories create trading-system-repo \
    --repository-format=docker \
    --location=${GCP_REGION} \
    --description="Docker repository for trading system services"
```

### d. Create Pub/Sub Topics

The Cloud Functions are triggered by Pub/Sub topics. You need to create these topics manually first.

```bash
# The topic for the data ingestion scheduler
gcloud pubsub topics create market-data-scheduler

# The topic that the risk model's output triggers
gcloud pubsub topics create tcost.request.v1
```

## 2. CI/CD Setup: Creating the Cloud Build Trigger

Once the prerequisites are met, you can create the trigger.

1.  Navigate to the **Cloud Build** section in the Google Cloud Console.
2.  Go to the **Triggers** tab.
3.  Connect your Git repository (e.g., GitHub, Cloud Source Repositories).
4.  Click **Create trigger**.
5.  **Name:** Give your trigger a descriptive name (e.g., `deploy-trading-system`).
6.  **Event:** Choose the event that will start the build (e.g., **Push to a branch**).
7.  **Source:** Select your repository and the branch you want to deploy from (e.g., `^main$`).
8.  **Configuration:**
    -   Select **Cloud Build configuration file (yaml or json)**.
    -   **Location:** Set it to **Repository**.
    -   **Cloud Build file location:** Enter `/cloudbuild.yaml`.
9.  **Substitution variables (Optional):** The `cloudbuild.yaml` has default values for `_GCP_REGION` and `_ARTIFACT_REGISTRY_REPO`. You can override them here if needed.
10. Click **Create**.

Now, every time you push a commit to the `main` branch, this trigger will automatically execute the pipeline defined in `cloudbuild.yaml`, deploying any changes to your services.

## 3. Monorepo Strategy

The `cloudbuild.yaml` file is structured with unique IDs for each service's deployment steps (e.g., `deploy-alpha-model`). This structure makes it possible to configure your Cloud Build trigger to only run deployment steps for services whose source code has changed in a given commit. This is an advanced feature that can be configured in the trigger settings under "Included files filter" and "Substitution variables" to dynamically control which steps run.
