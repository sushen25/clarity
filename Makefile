.DEFAULT_GOAL := help

PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
NPM ?= npm
SUDO ?= sudo
DEV_PORT ?= 8000
APP_URL ?= $(strip $(shell sed -n 's/^[[:space:]]*PUBLIC_ORIGIN[[:space:]]*=[[:space:]]*//p' .env 2>/dev/null | tail -1 | tr -d '"'"'"'\r'))
BACKUP_DEST ?=
SERVICE ?=
USERNAME ?=
FULL_NAME ?=
REGISTRATION_NUMBER ?=
ROLE ?= clinician
ADMIN_USERNAME ?= admin
AWS_LOGIN_PROFILE ?= clarity-bedrock-login
AWS_PROFILE ?= clarity-bedrock

COMPOSE := $(SUDO) docker compose -f docker-compose.yml -f deploy/compose.aws-profile.yml
LOCAL_DATA_DIR := $(CURDIR)/data
LOCAL_STORAGE_DIR := $(CURDIR)/storage
RUN_DIR := $(CURDIR)/.run
DEV_API_PID := $(RUN_DIR)/api.pid
DEV_WORKER_PID := $(RUN_DIR)/worker.pid
LOAD_DOTENV := set -a; . ./.env; set +a;

.PHONY: help bootstrap env frontend-install frontend-build frontend-test test test-backend check personas template aws-login dev dev-api dev-worker dev-up dev-down dev-status dev-logs admin-local compose-config deploy deploy-update deploy-recreate deploy-down deploy-ps deploy-logs require-app-url deploy-health deploy-admin deploy-user backup reset-local-data

help:
	@printf '%s\n' \
	  'Clarity commands:' \
	  '' \
	  'Local development:' \
	  '  make bootstrap                 Create .venv, install Python/Node dependencies, and build the UI' \
	  '  make dev                       Build the UI then run Flask in the foreground on http://localhost:8000' \
	  '  make dev-worker                Run the local background worker in the foreground (second terminal)' \
	  '  make dev-up                    Start local Flask and worker in the background' \
	  '  make aws-login                 Refresh AWS login and verify the Bedrock runtime profile' \
	  '  make dev-down                  Stop only the local processes started by dev-up' \
	  '  make dev-status                Show local development process state' \
	  '  make dev-logs                  Follow local development logs' \
	  '  make admin-local USERNAME=... FULL_NAME="..."  Create the first local administrator' \
	  '' \
	  'Tests and fixtures:' \
	  '  make test                      Run backend and frontend tests' \
	  '  make personas                  Regenerate synthetic test personas' \
	  '  make template                  Rebuild the de-identified DOCX template' \
	  '' \
	  'Raspberry Pi / Docker deployment:' \
	  '  make compose-config            Validate the merged Docker Compose configuration' \
	  '  make deploy                    Build images and start/reconcile the deployed stack' \
	  '  make deploy-update             Pull a fast-forward Git update, build, and deploy' \
	  '  make deploy-recreate           Recreate containers after .env or credential-mount changes' \
	  '  make deploy-ps                 Show deployed service state' \
	  '  make deploy-logs [SERVICE=worker]  Show/follow privacy-filtered container logs' \
	  '  make deploy-health             Check web-container and public HTTPS health' \
	  '  make deploy-admin USERNAME=admin FULL_NAME="Clinical Administrator"  Create the first admin' \
	  '  make deploy-user USERNAME=jane.smith FULL_NAME="Dr Jane Smith" [REGISTRATION_NUMBER=...] [ROLE=clinician]' \
	  '  make backup BACKUP_DEST=/mnt/clarity-backup  Create an encrypted-volume backup' \
	  '  make deploy-down               Stop deployed containers without removing data or volumes' \
	  '' \
	  'Destructive local-only operation:' \
	  '  make reset-local-data CONFIRM=DELETE  Permanently delete local data/ and storage/ (not backups/)'

env:
	@if [ ! -f .env ]; then cp .env.example .env; echo 'Created .env from .env.example. Review it before use.'; else echo '.env already exists; leaving it unchanged.'; fi

bootstrap: env
	@python3 -m venv .venv
	@$(PIP) install -r requirements.txt
	@$(NPM) --prefix frontend ci
	@$(NPM) --prefix frontend run build
	@echo 'Local environment is ready. Run `make dev` and, in another terminal, `make dev-worker`.'

frontend-install:
	@$(NPM) --prefix frontend ci

frontend-build:
	@$(NPM) --prefix frontend run build

frontend-test:
	@$(NPM) --prefix frontend test

test-backend:
	@$(PYTHON) -m pytest

test: test-backend frontend-test

check: test

personas:
	@$(PYTHON) scripts/generate_test_personas.py

template:
	@$(PYTHON) scripts/build_template.py

aws-login:
	@aws login --profile "$(AWS_LOGIN_PROFILE)"
	@aws sts get-caller-identity --profile "$(AWS_PROFILE)"

dev: frontend-build
	@echo 'Starting Flask at http://localhost:$(DEV_PORT). Run `make dev-worker` in another terminal.'
	@$(LOAD_DOTENV) COOKIE_SECURE=false PUBLIC_ORIGIN=http://localhost:$(DEV_PORT) $(PYTHON) -m flask --app 'app:create_app()' run --debug --port $(DEV_PORT)

dev-api: dev

dev-worker:
	@echo 'Starting the local worker. It uses the provider configured in .env.'
	@$(LOAD_DOTENV) COOKIE_SECURE=false PUBLIC_ORIGIN=http://localhost:$(DEV_PORT) $(PYTHON) -m app.worker

dev-up: frontend-build
	@mkdir -p "$(RUN_DIR)"
	@if [ -f "$(DEV_API_PID)" ] && kill -0 "$$(cat "$(DEV_API_PID)")" 2>/dev/null; then echo 'Local API is already running. Run `make dev-status`.'; else rm -f "$(DEV_API_PID)"; $(LOAD_DOTENV) COOKIE_SECURE=false PUBLIC_ORIGIN=http://localhost:$(DEV_PORT) nohup "$(PYTHON)" -m flask --app 'app:create_app()' run --debug --port "$(DEV_PORT)" >"$(RUN_DIR)/api.log" 2>&1 & echo $$! >"$(DEV_API_PID)"; echo "Started local API (PID $$(cat "$(DEV_API_PID)"))."; fi
	@if [ -f "$(DEV_WORKER_PID)" ] && kill -0 "$$(cat "$(DEV_WORKER_PID)")" 2>/dev/null; then echo 'Local worker is already running. Run `make dev-status`.'; else rm -f "$(DEV_WORKER_PID)"; $(LOAD_DOTENV) COOKIE_SECURE=false PUBLIC_ORIGIN=http://localhost:$(DEV_PORT) nohup "$(PYTHON)" -m app.worker >"$(RUN_DIR)/worker.log" 2>&1 & echo $$! >"$(DEV_WORKER_PID)"; echo "Started local worker (PID $$(cat "$(DEV_WORKER_PID)"))."; fi
	@echo 'Open http://localhost:$(DEV_PORT). Run `make dev-logs` to follow logs.'

dev-down:
	@for pid_file in "$(DEV_API_PID)" "$(DEV_WORKER_PID)"; do if [ -f "$$pid_file" ]; then pid="$$(cat "$$pid_file")"; if kill -0 "$$pid" 2>/dev/null; then kill "$$pid" && echo "Stopped local process $$pid."; else echo "Removed stale PID file for $$pid."; fi; rm -f "$$pid_file"; fi; done

dev-status:
	@for label in 'API:$(DEV_API_PID)' 'worker:$(DEV_WORKER_PID)'; do name="$${label%%:*}"; pid_file="$${label#*:}"; if [ -f "$$pid_file" ] && kill -0 "$$(cat "$$pid_file")" 2>/dev/null; then echo "$$name running (PID $$(cat "$$pid_file"))."; else echo "$$name not running."; fi; done

dev-logs:
	@mkdir -p "$(RUN_DIR)" && touch "$(RUN_DIR)/api.log" "$(RUN_DIR)/worker.log"
	@tail -f "$(RUN_DIR)/api.log" "$(RUN_DIR)/worker.log"

admin-local:
	@if [ -z "$(USERNAME)" ] || [ -z "$(FULL_NAME)" ]; then echo 'Usage: make admin-local USERNAME=admin FULL_NAME="Clinical Administrator"'; exit 1; fi
	@$(PYTHON) manage.py create-admin --username "$(USERNAME)" --full-name "$(FULL_NAME)"

compose-config:
	@$(COMPOSE) config -q
	@echo 'Compose configuration is valid.'

deploy: compose-config
	@$(COMPOSE) build
	@$(COMPOSE) up -d
	@$(COMPOSE) ps

deploy-update:
	@git pull --ff-only
	@$(MAKE) deploy

deploy-recreate: compose-config
	@$(COMPOSE) up -d --force-recreate
	@$(COMPOSE) ps

deploy-down:
	@$(COMPOSE) stop
	@$(COMPOSE) ps

deploy-ps:
	@$(COMPOSE) ps

# APP_URL defaults to PUBLIC_ORIGIN in .env so a deployment cannot silently
# health-check or create accounts against the wrong host.
require-app-url:
	@if [ -z "$(APP_URL)" ]; then echo 'APP_URL is empty. Set PUBLIC_ORIGIN in .env, or run: make $(MAKECMDGOALS) APP_URL=https://your-domain'; exit 1; fi
	@case "$(APP_URL)" in https://*|http://*) ;; *) echo 'APP_URL must include the scheme, for example https://clarity.example.com (got: $(APP_URL)).'; exit 1;; esac

deploy-logs:
	@$(COMPOSE) logs -f --tail=100 $(SERVICE)

deploy-health: require-app-url
	@$(COMPOSE) exec web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"
	@curl --fail --show-error "$(APP_URL)/api/health"

deploy-admin:
	@if [ -z "$(USERNAME)" ] || [ -z "$(FULL_NAME)" ]; then echo 'Usage: make deploy-admin USERNAME=admin FULL_NAME="Clinical Administrator"'; exit 1; fi
	@$(COMPOSE) run --rm web python manage.py create-admin --username "$(USERNAME)" --full-name "$(FULL_NAME)"

deploy-user: require-app-url
	@if [ -z "$(USERNAME)" ] || [ -z "$(FULL_NAME)" ]; then echo 'Usage: make deploy-user USERNAME=jane.smith FULL_NAME="Dr Jane Smith" [REGISTRATION_NUMBER=PSY...] [ROLE=clinician]'; exit 1; fi
	@./scripts/create_user.sh --url "$(APP_URL)" --username "$(USERNAME)" --full-name "$(FULL_NAME)" --registration-number "$(REGISTRATION_NUMBER)" --role "$(ROLE)" --admin-username "$(ADMIN_USERNAME)"

backup:
	@if [ -z "$(BACKUP_DEST)" ]; then echo 'Usage: make backup BACKUP_DEST=/mnt/clarity-backup'; exit 1; fi
	@findmnt "$(BACKUP_DEST)" >/dev/null || { echo "Backup destination is not a mount point: $(BACKUP_DEST)"; exit 1; }
	@$(SUDO) $(PYTHON) scripts/backup.py --database data/app.db --storage storage --destination "$(BACKUP_DEST)"

reset-local-data:
	@if [ "$(CONFIRM)" != "DELETE" ]; then echo 'Refusing to delete local data without explicit confirmation.'; echo 'Stop Flask and the worker, then run: make reset-local-data CONFIRM=DELETE'; exit 1; fi
	@if [ "$(CURDIR)" = "/" ] || [ ! -f "$(CURDIR)/manage.py" ] || [ ! -f "$(CURDIR)/app/schema.sql" ]; then echo 'Safety check failed: run this target from the project root.'; exit 1; fi
	@if command -v lsof >/dev/null 2>&1 && [ -f "$(LOCAL_DATA_DIR)/app.db" ] && lsof "$(LOCAL_DATA_DIR)/app.db" >/dev/null 2>&1; then echo 'The database is still open. Stop Flask and the background worker first.'; exit 1; fi
	@rm -rf -- "$(LOCAL_DATA_DIR)" "$(LOCAL_STORAGE_DIR)"
	@mkdir -p "$(LOCAL_DATA_DIR)" "$(LOCAL_STORAGE_DIR)"
	@echo 'Local database and case storage removed. Backups were not deleted.'
	@echo 'Next: make admin-local USERNAME=admin FULL_NAME="Clinical Administrator"'
