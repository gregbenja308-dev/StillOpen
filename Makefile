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
deploy: ## Cloud Run from source (Still Open GCP project only)
	gcloud run deploy stillopen \
		--source . \
		--region $${GOOGLE_CLOUD_REGION:-us-central1} \
		--allow-unauthenticated \
		--set-env-vars STILLOPEN_ENV=cloud,GOOGLE_CLOUD_PROJECT=$${GOOGLE_CLOUD_PROJECT}

.PHONY: scheduler
scheduler: ## Create a 30-min Watch tick (requires Cloud Run URL + STILLOPEN_JOB_TOKEN)
	@test -n "$(URL)" || (echo "URL=https://….run.app required" && exit 1)
	gcloud scheduler jobs create http stillopen-watch \
		--location $${GOOGLE_CLOUD_REGION:-us-central1} \
		--schedule "*/30 * * * *" \
		--uri "$(URL)/v1/jobs/watch" \
		--http-method POST \
		--headers "X-Stillopen-Job-Token=$${STILLOPEN_JOB_TOKEN}" \
		--attempt-deadline 120s
