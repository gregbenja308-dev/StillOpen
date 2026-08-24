.DEFAULT_GOAL := help

UV := $(shell if [ -x .tools/uv ]; then echo .tools/uv; else echo uv; fi)

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install Python deps via uv workspaces
	$(UV) sync --all-extras --group dev

.PHONY: env
env: ## Bootstrap .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env — paste GOOGLE_API_KEY; generate STILLOPEN_TOKEN_KEY")

.PHONY: token-key
token-key: ## Print a new Fernet key for STILLOPEN_TOKEN_KEY (do not commit)
	$(UV) run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

.PHONY: fmt
fmt: ## Auto-format with ruff
	$(UV) run ruff format packages tests
	$(UV) run ruff check --fix packages tests

.PHONY: lint
lint: ## Lint (ruff + mypy)
	$(UV) run ruff check packages tests
	$(UV) run ruff format --check packages tests
	$(UV) run mypy packages

.PHONY: test
test: ## Run the test suite (no network, no keys)
	$(UV) run pytest -x

.PHONY: check
check: lint test ## Lint + test

.PHONY: api
api: ## Run the FastAPI service locally
	$(UV) run uvicorn stillopen_api.main:app --reload --host 127.0.0.1 --port 8080

.PHONY: job-watch
job-watch: ## Run the Watch tick locally (no network fetch)
	$(UV) run python -m stillopen_jobs.watch

.PHONY: ext
ext: ## Build the Chrome MV3 extension (TypeScript / WXT)
	npm --prefix packages/ext install
	npm --prefix packages/ext run build

.PHONY: ext-dev
ext-dev: ## Extension HMR (broken after outDir=dist — use make ext)
	npm --prefix packages/ext run dev

.PHONY: deploy
deploy: ## Cloud Run from source (Vertex + Firestore + Cloud Trace)
	@test -n "$${GOOGLE_CLOUD_PROJECT}" || (echo "Set GOOGLE_CLOUD_PROJECT" && exit 1)
	gcloud run deploy stillopen \
		--source . \
		--project $${GOOGLE_CLOUD_PROJECT} \
		--region $${GOOGLE_CLOUD_REGION:-us-central1} \
		--allow-unauthenticated \
		--set-env-vars STILLOPEN_ENV=cloud,GOOGLE_CLOUD_PROJECT=$${GOOGLE_CLOUD_PROJECT},GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_REGION=$${GOOGLE_CLOUD_REGION:-us-central1},GOOGLE_CLOUD_LOCATION=$${GOOGLE_CLOUD_LOCATION:-global},STILLOPEN_OTEL_EXPORTER=gcp,STILLOPEN_LIVE_GOOGLE=1,STILLOPEN_FAST_MODEL=gemini-3.5-flash,STILLOPEN_REASONING_MODEL=gemini-3.5-pro

.PHONY: cloud-apis
cloud-apis: ## Enable Cloud Run, Vertex, Firestore, Scheduler, Secret Manager, Trace
	@test -n "$${GOOGLE_CLOUD_PROJECT}" || (echo "Set GOOGLE_CLOUD_PROJECT" && exit 1)
	gcloud services enable \
		run.googleapis.com \
		aiplatform.googleapis.com \
		firestore.googleapis.com \
		cloudscheduler.googleapis.com \
		secretmanager.googleapis.com \
		cloudtrace.googleapis.com \
		--project $${GOOGLE_CLOUD_PROJECT}

.PHONY: cloud-iam
cloud-iam: ## Grant the Cloud Run default SA Vertex, Firestore, secrets, Trace
	@test -n "$${GOOGLE_CLOUD_PROJECT}" || (echo "Set GOOGLE_CLOUD_PROJECT" && exit 1)
	@num=$$(gcloud projects describe $${GOOGLE_CLOUD_PROJECT} --format='value(projectNumber)'); \
	sa="$${num}-compute@developer.gserviceaccount.com"; \
	for role in roles/aiplatform.user roles/datastore.user roles/secretmanager.secretAccessor roles/cloudtrace.agent roles/storage.objectAdmin roles/artifactregistry.writer roles/logging.logWriter; do \
	  gcloud projects add-iam-policy-binding $${GOOGLE_CLOUD_PROJECT} --member="serviceAccount:$${sa}" --role="$${role}" --condition=None >/dev/null; \
	done; \
	echo "IAM granted to $${sa}"

.PHONY: secrets-init
secrets-init: ## Create Secret Manager ids (job token + Fernet key) if missing
	@test -n "$${GOOGLE_CLOUD_PROJECT}" || (echo "Set GOOGLE_CLOUD_PROJECT" && exit 1)
	@if ! gcloud secrets describe stillopen-token-key --project $${GOOGLE_CLOUD_PROJECT} >/dev/null 2>&1; then \
	  $(UV) run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode(), end='')" | \
	    gcloud secrets create stillopen-token-key --data-file=- --project $${GOOGLE_CLOUD_PROJECT}; \
	fi
	@if ! gcloud secrets describe stillopen-job-token --project $${GOOGLE_CLOUD_PROJECT} >/dev/null 2>&1; then \
	  python3 -c "import secrets; print(secrets.token_urlsafe(32), end='')" | \
	    gcloud secrets create stillopen-job-token --data-file=- --project $${GOOGLE_CLOUD_PROJECT}; \
	fi
	@echo "Secrets ready: stillopen-token-key, stillopen-job-token"

.PHONY: scheduler
scheduler: ## Create or update the 30-min Watch tick (URL=https://….run.app)
	@test -n "$(URL)" || (echo "URL=https://….run.app required" && exit 1)
	@test -n "$${STILLOPEN_JOB_TOKEN}" || (echo "STILLOPEN_JOB_TOKEN required" && exit 1)
	gcloud scheduler jobs update http stillopen-watch \
		--location $${GOOGLE_CLOUD_REGION:-us-central1} \
		--schedule "*/30 * * * *" \
		--uri "$(URL)/v1/jobs/watch" \
		--http-method POST \
		--update-headers "X-Stillopen-Job-Token=$${STILLOPEN_JOB_TOKEN}" \
		--attempt-deadline 120s \
		--project $${GOOGLE_CLOUD_PROJECT} \
	|| gcloud scheduler jobs create http stillopen-watch \
		--location $${GOOGLE_CLOUD_REGION:-us-central1} \
		--schedule "*/30 * * * *" \
		--uri "$(URL)/v1/jobs/watch" \
		--http-method POST \
		--headers "X-Stillopen-Job-Token=$${STILLOPEN_JOB_TOKEN}" \
		--attempt-deadline 120s \
		--project $${GOOGLE_CLOUD_PROJECT}
